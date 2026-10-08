"""Local, workspace-scoped reading records; source identities remain immutable."""
import copy
import json
import math
import re

import backend as b


STATE_LIMIT = 4 * 1024 * 1024
RECORD_LIMIT = 1000
COLORS = {'yellow', 'green', 'blue', 'pink', 'purple'}
VIEWS = {'read', 'library', 'write', 'notes', 'evidence', 'discover', 'matrix', 'ask', 'tools'}
SOURCE_FIELDS = {'document_id', 'tags', 'collection', 'status', 'favorite', 'last_page'}
RESUME_FIELDS = {'document_id', 'page', 'note_id', 'view', 'panel', 'next_action'}
ANNOTATION_FIELDS = {'id', 'document_id', 'page', 'quote', 'comment', 'color', 'word_indices', 'rects', 'source_sha256', 'archived', 'created_at', 'updated_at'}
CLAIM_FIELDS = {'id', 'note_id', 'note_version', 'claim_anchor', 'status', 'document_id', 'page', 'excerpt', 'source_sha256', 'attachment_history', 'archived', 'created_at', 'updated_at'}
HISTORY_FIELDS = {'document_id', 'page', 'excerpt', 'source_sha256', 'status', 'replaced_at', 'reading_version'}


def _integer(value, label, minimum=0, maximum=1_000_000):
    if type(value) is not int or not minimum <= value <= maximum:
        raise b.AppError(label + ' is outside its supported integer range.')
    return value


def _boolean(value, label):
    if type(value) is not bool:
        raise b.AppError(label + ' must be true or false.')
    return value


def _enum(value, choices, label):
    if not isinstance(value, str) or value not in choices:
        raise b.AppError(label + ' is not a supported value.')
    return value


def _keys(value, allowed, label, required=()):
    if not isinstance(value, dict) or set(value) - allowed or set(required) - set(value):
        raise b.AppError(label + ' has missing or unsupported fields.')


def _normalized(text):
    return ' '.join(text.split())


def _default_source(document_id):
    return {'document_id': document_id, 'tags': [], 'collection': '', 'status': 'unread', 'favorite': False, 'last_page': 1}


def _default_state(workspace_id):
    return {'schema_version': 1, 'workspace_id': workspace_id, 'version': 0, 'sources': [],
            'resume': {'document_id': None, 'page': 1, 'note_id': None, 'view': 'read', 'panel': '', 'next_action': ''},
            'annotations': [], 'claims': []}


def _source_fields(source):
    _keys(source, SOURCE_FIELDS, 'Reading source', SOURCE_FIELDS)
    b.identifier(source['document_id'])
    if not isinstance(source['tags'], list) or len(source['tags']) > 50:
        raise b.AppError('Tags must be a list of at most 50 strings.')
    for tag in source['tags']:
        b.text_value(tag, 'Tag', 80, False)
    if len(set(source['tags'])) != len(source['tags']):
        raise b.AppError('Tags must be unique.')
    b.text_value(source['collection'], 'Collection', 120)
    _enum(source['status'], {'unread', 'reading', 'read'}, 'Reading status')
    _boolean(source['favorite'], 'Favorite')
    _integer(source['last_page'], 'Last page', 1, b.PAGE_LIMIT)


def _resume_fields(resume):
    _keys(resume, RESUME_FIELDS, 'Resume position', RESUME_FIELDS)
    for field in ('document_id', 'note_id'):
        if resume[field] is not None:
            b.identifier(resume[field])
    _integer(resume['page'], 'Resume page', 1, b.PAGE_LIMIT)
    _enum(resume['view'], VIEWS, 'Resume view')
    b.text_value(resume['panel'], 'Resume panel', 80)
    b.text_value(resume['next_action'], 'Next action', 2000)


def _attachment_fields(record):
    if record['document_id'] is None:
        if record['page'] is not None or record['excerpt'] or record['source_sha256']:
            raise b.AppError('An unattached claim cannot contain a source location or excerpt.')
        if record['status'] != 'needs_source':
            raise b.AppError('Attach an exact source passage before marking a claim attached or checked.')
    else:
        b.identifier(record['document_id'])
        _integer(record['page'], 'Claim page', 1, b.PAGE_LIMIT)
        b.text_value(record['excerpt'], 'Claim excerpt', b.CITATION_EXCERPT_LIMIT, False)
        _digest(record['source_sha256'])


def _digest(value):
    if not isinstance(value, str) or not re.fullmatch('[a-f0-9]{64}', value):
        raise b.AppError('Reading source hash is invalid.')


def _record_fields(record, kind):
    fields = ANNOTATION_FIELDS if kind == 'annotation' else CLAIM_FIELDS
    _keys(record, fields, 'Reading ' + kind, fields)
    b.identifier(record['id'])
    _boolean(record['archived'], 'Archived')
    for field in ('created_at', 'updated_at'):
        b.text_value(record[field], 'Reading record date', 100, False)
    if kind == 'annotation':
        b.identifier(record['document_id'])
        _integer(record['page'], 'Annotation page', 1, b.PAGE_LIMIT)
        b.text_value(record['quote'], 'Annotation quote', b.CITATION_EXCERPT_LIMIT, False)
        b.text_value(record['comment'], 'Annotation comment', 8000)
        _enum(record['color'], COLORS, 'Annotation color')
        _digest(record['source_sha256'])
        indices = record['word_indices']
        if not isinstance(indices, list) or len(indices) > 2000:
            raise b.AppError('PDF selection supports at most 2,000 word indices.')
        for index in indices:
            _integer(index, 'PDF word index', 0, 19_999)
        if indices and indices != list(range(indices[0], indices[-1] + 1)):
            raise b.AppError('PDF selection must contain consecutive ordered word indices.')
        rects = record['rects']
        if not isinstance(rects, list) or len(rects) != len(indices):
            raise b.AppError('Annotation geometry must correspond to its PDF words.')
        for rect in rects:
            if not isinstance(rect, list) or len(rect) != 4 or any(type(value) not in {int, float} or not math.isfinite(value) or not 0 <= value <= 1 for value in rect) or rect[0] >= rect[2] or rect[1] >= rect[3]:
                raise b.AppError('Annotation geometry must use positive normalized rectangles.')
    else:
        b.identifier(record['note_id'])
        _integer(record['note_version'], 'Claim note version', 1)
        b.text_value(record['claim_anchor'], 'Exact claim anchor', 4000, False)
        _enum(record['status'], {'needs_source', 'attached', 'checked'}, 'Claim status')
        _attachment_fields(record)
        history = record['attachment_history']
        if not isinstance(history, list) or len(history) > 50:
            raise b.AppError('A claim supports at most 50 retained source-attachment changes. Earlier history was preserved.', 413)
        for attachment in history:
            _keys(attachment, HISTORY_FIELDS, 'Claim attachment history', HISTORY_FIELDS)
            _enum(attachment['status'], {'needs_source', 'attached', 'checked'}, 'Historical claim status')
            _attachment_fields(attachment)
            if attachment['document_id'] is None:
                raise b.AppError('Historical attachments must retain a source.')
            b.text_value(attachment['replaced_at'], 'Attachment history date', 100, False)
            _integer(attachment['reading_version'], 'Attachment history version', 1)


def validate_backup(state, workspace_id, documents, notes, originals=None, page_limits=None, geometry_reader=None):
    """Validate all nested identities before restore publishes any original or row."""
    if state is None:
        return _default_state(workspace_id)
    allowed = {'schema_version', 'workspace_id', 'version', 'sources', 'resume', 'annotations', 'claims'}
    _keys(state, allowed, 'Backup reading state', allowed)
    if type(state['schema_version']) is not int or state['schema_version'] != 1 or state['workspace_id'] != workspace_id:
        raise b.AppError('Backup reading schema or workspace is invalid.')
    _integer(state['version'], 'Reading version')
    if len(json.dumps(state, ensure_ascii=False).encode()) > STATE_LIMIT:
        raise b.AppError('Reading state exceeds its 4 MB limit.', 413)
    docs = {document['id']: document for document in documents}
    note_ids = {note['id'] for note in notes}
    seen = set()
    for key in ('sources', 'annotations', 'claims'):
        records = state[key]
        if not isinstance(records, list) or len(records) > RECORD_LIMIT:
            raise b.AppError('Reading collections support at most 1,000 records each.', 413)
        for record in records:
            if key == 'sources':
                _source_fields(record)
                identity = ('source', record['document_id'])
            else:
                _record_fields(record, 'annotation' if key == 'annotations' else 'claim')
                identity = ('record', record['id'])
                if record['id'] in docs or record['id'] in note_ids:
                    raise b.AppError('Reading record identity conflicts with a source or note.')
            if identity in seen:
                raise b.AppError('Reading record identity is duplicated.')
            seen.add(identity)
            document_id = record.get('document_id')
            if document_id is not None and document_id not in docs:
                raise b.AppError('Reading record references a missing source.')
            if key == 'claims' and record['note_id'] not in note_ids:
                raise b.AppError('Claim record references a missing note.')
            if key == 'claims':
                for attachment in record['attachment_history']:
                    historical_doc = docs.get(attachment['document_id'])
                    if historical_doc is None or historical_doc['sha256'] != attachment['source_sha256']:
                        raise b.AppError('Claim attachment history references a missing or changed original.')
                    historical_limit = (page_limits or {}).get(historical_doc['id'], max(1, historical_doc.get('pages', 0))) if historical_doc['kind'] == 'pdf' else 1
                    if attachment['page'] > historical_limit:
                        raise b.AppError('Claim attachment history page is outside its source.')
            if key != 'sources' and document_id is not None and record['source_sha256'] != docs[document_id]['sha256']:
                raise b.AppError('Reading record source identity does not match the retained original.')
            if key == 'annotations' and docs[document_id]['kind'] != 'pdf' and (record['word_indices'] or record['rects']):
                raise b.AppError('Extracted sections cannot contain PDF geometry.')
            if document_id is not None:
                page = record.get('page', record.get('last_page'))
                limit = (page_limits or {}).get(document_id, max(1, docs[document_id].get('pages', 0))) if docs[document_id]['kind'] == 'pdf' else 1
                if page > limit:
                    raise b.AppError('Reading record is outside the source page range.')
            if key == 'annotations' and docs[document_id]['kind'] == 'pdf':
                if b.pdf_lib is None or originals is None:
                    raise b.AppError('This backup contains PDF annotations that require local PyMuPDF for geometry verification. No workspace was created.')
                geometry = (geometry_reader or Reading._geometry_bytes)(originals[document_id], document_id, record['page'])
                indices = record['word_indices']
                if not indices or any(index >= len(geometry['words']) for index in indices):
                    raise b.AppError('Backup annotation word selection is invalid.')
                words = [geometry['words'][index] for index in indices]
                if _normalized(record['quote']) != ' '.join(word['text'] for word in words) or any(abs(actual - saved) > 0.00001 for word, rect in zip(words, record['rects']) for actual, saved in zip(word['rect'], rect)):
                    raise b.AppError('Backup annotation geometry or quote does not match the retained original.')
    _resume_fields(state['resume'])
    resume = state['resume']
    if resume['document_id'] is not None and resume['document_id'] not in docs or resume['note_id'] is not None and resume['note_id'] not in note_ids:
        raise b.AppError('Resume position references a missing source or note.')
    if resume['document_id'] is None and resume['page'] != 1:
        raise b.AppError('A resume page requires a source.')
    if resume['document_id'] is not None:
        doc = docs[resume['document_id']]
        if resume['page'] > ((page_limits or {}).get(doc['id'], max(1, doc.get('pages', 0))) if doc['kind'] == 'pdf' else 1):
            raise b.AppError('Resume page is outside the source page range.')
    return copy.deepcopy(state)


def remap_backup(state, workspace_id, mapping, remap_refs):
    result = copy.deepcopy(state)
    result['workspace_id'] = workspace_id
    for record in result['sources'] + result['annotations'] + result['claims'] + [result['resume']]:
        for key in ('document_id', 'note_id'):
            if record.get(key) is not None:
                record[key] = mapping[record[key]]
        if 'id' in record:
            record['id'] = b.new_id()
        if 'claim_anchor' in record:
            record['claim_anchor'] = remap_refs(record['claim_anchor'])
            for attachment in record['attachment_history']:
                attachment['document_id'] = mapping[attachment['document_id']]
    return result


class Reading:
    def __init__(self, store):
        self.store = store

    @staticmethod
    def supports(method, route):
        return method == 'GET' and route in {'/api/reading', '/api/reading/geometry', '/api/reading/duplicates'} or method == 'POST' and route in {'/api/reading/source', '/api/reading/resume', '/api/reading/annotation', '/api/reading/claim'}

    @staticmethod
    def key(workspace_id):
        return 'reading:v1:' + workspace_id

    def load(self, workspace_id):
        self.store._workspace(workspace_id)
        row = self.store.db.execute('SELECT value FROM settings WHERE key=?', (self.key(workspace_id),)).fetchone()
        return json.loads(row[0]) if row else _default_state(workspace_id)

    def save(self, state):
        if len(json.dumps(state, ensure_ascii=False).encode()) > STATE_LIMIT:
            raise b.AppError('Reading state exceeds its 4 MB limit. Existing records were retained.', 413)
        if any(len(state[key]) > RECORD_LIMIT for key in ('sources', 'annotations', 'claims')):
            raise b.AppError('Reading collections support at most 1,000 records each. Existing records were retained.', 413)
        self.store.db.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (self.key(state['workspace_id']), json.dumps(state, ensure_ascii=False)))

    def _note(self, note_id, workspace_id):
        b.identifier(note_id)
        row = self.store.db.execute('SELECT * FROM notes WHERE id=? AND workspace_id=?', (note_id, workspace_id)).fetchone()
        if row is None:
            raise b.AppError('Note not found in this workspace.', 404)
        return dict(row)

    def _page(self, document, page):
        _integer(page, 'Source page', 1, b.PAGE_LIMIT)
        if document['kind'] != 'pdf' and page != 1:
            raise b.AppError('This source exposes one extracted section, not PDF pages.')
        if document['kind'] == 'pdf' and page > document['pages']:
            raise b.AppError('Source page is outside the PDF file.')

    def geometry(self, workspace_id, document_id, page):
        document = self.store._document(document_id, workspace_id)
        if document['kind'] != 'pdf' or b.pdf_lib is None:
            raise b.AppError('Selectable geometry requires a readable PDF and local PyMuPDF.')
        self._page(document, page)
        return self._geometry_bytes(self.store._bytes(document), document_id, page)

    @staticmethod
    def _geometry_bytes(data, document_id, page_number):
        try:
            with b.pdf_lib.open(stream=data, filetype='pdf') as pdf:
                if pdf.needs_pass or not 1 <= page_number <= len(pdf):
                    raise b.AppError('PDF page is unavailable.')
                page = pdf[page_number - 1]
                bounds = page.rect
                words = page.get_text('words', sort=True)
                if len(words) > 20_000:
                    raise b.AppError('PDF page exceeds the 20,000-word selection limit.', 413)
                output = []
                for word in words:
                    rect = (b.pdf_lib.Rect(word[:4]) * page.rotation_matrix) & bounds
                    if rect.is_empty:
                        continue
                    normalized = [(rect.x0 - bounds.x0) / bounds.width, (rect.y0 - bounds.y0) / bounds.height,
                                  (rect.x1 - bounds.x0) / bounds.width, (rect.y1 - bounds.y0) / bounds.height]
                    output.append({'index': len(output), 'text': word[4], 'rect': normalized, 'block': word[5], 'line': word[6]})
                return {'document_id': document_id, 'page': page_number, 'width': bounds.width, 'height': bounds.height, 'words': output}
        except b.AppError:
            raise
        except Exception:
            raise b.AppError('PDF text geometry could not be read. The original was retained.') from None

    def _excerpt(self, workspace_id, document_id, page, text):
        document = self.store._document(document_id, workspace_id)
        self._page(document, page)
        data = self.store._bytes(document)
        if document['metadata'].get('catalogue_source') or document['kind'] in {'bib', 'ris', 'png', 'jpg', 'jpeg', 'webp'}:
            raise b.AppError('Attach a passage from imported source text; bibliography and image records are not evidence text.')
        if not self._contains(document, page, text, data):
            raise b.AppError('The quoted passage is not present on this source page/section.')
        return document

    def _contains(self, document, page, text, data):
        row = self.store.db.execute('SELECT text FROM pages WHERE document_id=? AND page=?', (document['id'], page)).fetchone()
        if row is not None and _normalized(text) in _normalized(row['text']):
            return True
        return document['kind'] == 'pdf' and _normalized(text) in ' '.join(word['text'] for word in self._geometry_bytes(data, document['id'], page)['words'])

    def public(self, state):
        result = copy.deepcopy(state)
        sources = {source['document_id']: source for source in result['sources']}
        result['sources'] = [sources.get(row['id'], _default_source(row['id'])) for row in self.store.db.execute('SELECT id FROM documents WHERE workspace_id=? ORDER BY created_at,id', (state['workspace_id'],))]
        source_stale = {}
        verified_sources = {}
        for record in result['annotations'] + result['claims']:
            reasons = []
            if record.get('document_id'):
                document_id = record['document_id']
                if document_id not in source_stale:
                    try:
                        document = self.store._document(document_id, state['workspace_id'])
                        verified_sources[document_id] = (document, self.store._bytes(document))
                        source_stale[document_id] = False
                    except b.AppError:
                        source_stale[document_id] = True
                if source_stale[document_id]:
                    reasons.append('managed_source_changed_or_unavailable')
                else:
                    document, data = verified_sources[document_id]
                    quote = record.get('excerpt', record.get('quote'))
                    try:
                        matches = self._contains(document, record['page'], quote, data)
                    except b.AppError:
                        matches = False
                    if not matches:
                        reasons.append('source_excerpt_changed' if 'excerpt' in record else 'source_quote_changed')
            if 'note_id' in record:
                note = self._note(record['note_id'], state['workspace_id'])
                if note['version'] != record['note_version']:
                    reasons.append('note_version_changed')
                if record['claim_anchor'] not in note['body']:
                    reasons.append('claim_anchor_changed')
            record['stale'], record['stale_reasons'] = bool(reasons), reasons
        return result

    def dispatch(self, method, route, payload):
        allowed = {'workspace_id'}
        if method == 'GET':
            if route.endswith('/geometry'):
                _keys(payload, allowed | {'document_id', 'page'}, 'PDF geometry request', {'workspace_id', 'document_id', 'page'})
                self.store._workspace(payload['workspace_id'])
                page = payload['page']
                if not isinstance(page, str) or not re.fullmatch(r'[1-9]\d{0,2}', page):
                    raise b.AppError('PDF page must be a one-based integer.')
                return self.geometry(payload['workspace_id'], payload['document_id'], int(page))
            _keys(payload, allowed, 'Reading request', allowed)
            state = self.load(payload['workspace_id'])
            return self.duplicates(payload['workspace_id']) if route.endswith('/duplicates') else self.public(state)
        operation = route.rsplit('/', 1)[-1]
        fields = SOURCE_FIELDS if operation == 'source' else RESUME_FIELDS if operation == 'resume' else {'id', 'document_id', 'page', 'quote', 'comment', 'color', 'word_indices', 'archived'} if operation == 'annotation' else {'id', 'note_id', 'note_version', 'claim_anchor', 'status', 'document_id', 'page', 'excerpt', 'archived'}
        _keys(payload, allowed | {'expected_version'} | fields, 'Reading write', {'workspace_id', 'expected_version'})
        state = self.load(payload['workspace_id'])
        _integer(payload['expected_version'], 'Expected reading version')
        if payload['expected_version'] != state['version']:
            raise b.AppError('Reading records changed in another window. Reload them and review your pending change.', 409)
        previous = copy.deepcopy(state)
        changes = {key: value for key, value in payload.items() if key not in {'workspace_id', 'expected_version'}}
        if operation == 'source':
            document = self.store._document(changes.get('document_id'), state['workspace_id'])
            old = next((row for row in state['sources'] if row['document_id'] == document['id']), None)
            source = {**(old or _default_source(document['id'])), **changes}
            _source_fields(source)
            self._page(document, source['last_page'])
            if old is None:
                state['sources'].append(source)
            else:
                old.update(source)
        elif operation == 'resume':
            resume = {**state['resume'], **changes}
            _resume_fields(resume)
            if resume['document_id'] is not None:
                self._page(self.store._document(resume['document_id'], state['workspace_id']), resume['page'])
            elif resume['page'] != 1:
                raise b.AppError('A resume page requires a source.')
            if resume['note_id'] is not None:
                self._note(resume['note_id'], state['workspace_id'])
            state['resume'] = resume
        else:
            self._record(state, operation, changes)
        if state == previous:
            return self.public(state)
        if state['version'] >= 1_000_000:
            raise b.AppError('Reading version limit reached. Existing records were retained.', 409)
        state['version'] += 1
        with self.store.db:
            self.save(state)
        return self.public(state)

    def _record(self, state, kind, changes):
        records = state['annotations' if kind == 'annotation' else 'claims']
        if 'id' in changes:
            b.identifier(changes['id'])
            record = next((row for row in records if row['id'] == changes['id']), None)
            if record is None:
                raise b.AppError('Reading record not found in this workspace.', 404)
            mutable = {'id', 'comment', 'color', 'archived'} if kind == 'annotation' else {'id', 'status', 'document_id', 'page', 'excerpt', 'archived'}
            _keys(changes, mutable, 'Reading record update')
            if kind == 'claim':
                changed_attachment = any(key in changes and changes[key] != record[key] for key in ('document_id', 'page', 'excerpt'))
                if changed_attachment and record['status'] == 'checked':
                    if changes.get('status') == 'checked':
                        raise b.AppError('A changed source attachment must be reviewed again before marking it checked.', 409)
                    changes.setdefault('status', 'attached' if changes.get('document_id', record['document_id']) is not None else 'needs_source')
                if changed_attachment and record['document_id'] is not None:
                    record['attachment_history'].append({**{key: record[key] for key in ('document_id', 'page', 'excerpt', 'source_sha256', 'status')}, 'replaced_at': b.now(), 'reading_version': state['version'] + 1})
            if any(record.get(key) != value for key, value in changes.items()):
                record.update(changes)
                record['updated_at'] = b.now()
        else:
            stamp = b.now()
            common = {'id': b.new_id(), 'archived': False, 'created_at': stamp, 'updated_at': stamp}
            if kind == 'annotation':
                record = {**common, 'comment': '', 'color': 'yellow', 'word_indices': [], 'rects': [], **changes, 'source_sha256': ''}
                required = {'document_id', 'page', 'quote'}
            else:
                record = {**common, 'document_id': None, 'page': None, 'excerpt': '', 'source_sha256': '', 'attachment_history': [], **changes}
                required = {'note_id', 'note_version', 'claim_anchor', 'status'}
            _keys(changes, ANNOTATION_FIELDS if kind == 'annotation' else CLAIM_FIELDS, 'Reading record creation', required)
            if kind == 'claim':
                note = self._note(record['note_id'], state['workspace_id'])
                _integer(record['note_version'], 'Claim note version', 1)
                anchor = b.text_value(record['claim_anchor'], 'Exact claim anchor', 4000, False)
                if record['note_version'] != note['version']:
                    raise b.AppError('The saved note changed. Save or reload before recording this claim.', 409)
                if anchor not in note['body']:
                    raise b.AppError('Select an exact claim from the saved note.')
            records.append(record)
        if kind == 'annotation':
            if 'id' not in changes:
                quote = b.text_value(record['quote'], 'Annotation quote', b.CITATION_EXCERPT_LIMIT, False)
                document = self.store._document(record['document_id'], state['workspace_id'])
                self._page(document, record['page'])
                record['source_sha256'] = document['sha256']
                if document['kind'] == 'pdf':
                    geometry = self.geometry(state['workspace_id'], document['id'], record['page'])
                    indices = record['word_indices']
                    if not isinstance(indices, list) or not indices or len(indices) > 2000 or any(type(index) is not int or not 0 <= index < len(geometry['words']) for index in indices) or indices != list(range(indices[0], indices[-1] + 1)):
                        raise b.AppError('Select consecutive actual PDF words to create a highlight.')
                    selected = [geometry['words'][index] for index in indices]
                    if _normalized(quote) != ' '.join(word['text'] for word in selected):
                        raise b.AppError('The quote must match the selected PDF words.')
                    record['rects'] = [word['rect'] for word in selected]
                else:
                    self._excerpt(state['workspace_id'], document['id'], record['page'], quote)
            _record_fields(record, kind)
        else:
            if changes.get('status') == 'checked':
                note = self._note(record['note_id'], state['workspace_id'])
                if note['version'] != record['note_version'] or record['claim_anchor'] not in note['body']:
                    raise b.AppError('The saved claim changed. Record and review its current wording before marking it checked.', 409)
            validate_attachment = 'id' not in changes or bool({'document_id', 'page', 'excerpt'} & set(changes)) or changes.get('status') in {'attached', 'checked'}
            if record['document_id'] is not None and validate_attachment:
                text = b.text_value(record['excerpt'], 'Claim excerpt', b.CITATION_EXCERPT_LIMIT, False)
                document = self._excerpt(state['workspace_id'], record['document_id'], record['page'], text)
                record['source_sha256'] = document['sha256']
            elif record['document_id'] is None:
                record['source_sha256'] = ''
            _record_fields(record, kind)

    def duplicates(self, workspace_id):
        documents = [self.store._public_doc(self.store._document(row['id'])) for row in self.store.db.execute('SELECT id FROM documents WHERE workspace_id=? ORDER BY created_at,id', (workspace_id,))]
        groups = {}
        for document in documents:
            metadata = document['metadata']
            doi = re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi\s*:\s*)', '', metadata.get('doi', '').strip(), flags=re.I).casefold()
            title = _normalized(metadata.get('title', '')).casefold()
            for reason, value in (('doi', doi), ('title', title)):
                if value:
                    groups.setdefault((reason, value), []).append(document['id'])
        pairs = {}
        for (reason, _), ids in groups.items():
            for first in range(len(ids)):
                for second in range(first + 1, len(ids)):
                    pair = (ids[first], ids[second])
                    pairs.setdefault(pair, []).append(reason)
                    if len(pairs) > RECORD_LIMIT:
                        raise b.AppError('Duplicate review exceeds 1,000 candidate pairs. Narrow the workspace; no originals were changed.', 413)
        return {'workspace_id': workspace_id, 'candidates': [{'document_ids': list(pair), 'reasons': reasons} for pair, reasons in pairs.items()],
                'notice': 'Entered/imported metadata matches are review candidates only. Originals and citation IDs are retained.'}
