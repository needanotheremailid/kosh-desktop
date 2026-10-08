"""Manual reviewer-response records; saved manuscripts are never mutated here."""
import copy
import json

import backend as b


STATE_LIMIT = 4 * 1024 * 1024
RECORD_LIMIT = 1000
HISTORY_LIMIT = 200
STATUSES = {'open', 'planned', 'revised', 'responded'}
ANCHOR_FIELDS = {'note_version', 'passage_start', 'passage_end', 'passage'}
EDIT_FIELDS = {'reviewer', 'comment', 'planned_text', 'revised_text', 'response', 'status', 'archived'}
SNAPSHOT_FIELDS = ANCHOR_FIELDS | EDIT_FIELDS
RECORD_FIELDS = SNAPSHOT_FIELDS | {'id', 'note_id', 'created_at', 'updated_at', 'history'}
HISTORY_FIELDS = SNAPSHOT_FIELDS | {'replaced_at', 'reviewer_version'}
STATE_FIELDS = {'schema_version', 'workspace_id', 'version', 'comments'}


def _keys(value, allowed, label, required=()):
    if not isinstance(value, dict) or set(value) - allowed or set(required) - set(value):
        raise b.AppError(label + ' has missing or unsupported fields.')


def _integer(value, label, minimum=0, maximum=1_000_000):
    if type(value) is not int or not minimum <= value <= maximum:
        raise b.AppError(label + ' is outside its supported integer range.')


def _default(workspace_id):
    return {'schema_version': 1, 'workspace_id': workspace_id, 'version': 0, 'comments': []}


def _snapshot_fields(record):
    _integer(record['note_version'], 'Saved manuscript version', 1)
    _integer(record['passage_start'], 'Passage start', 0, 200_000)
    _integer(record['passage_end'], 'Passage end', 1, 200_000)
    b.text_value(record['passage'], 'Exact saved manuscript passage', 20_000, False)
    if record['passage_end'] - record['passage_start'] != len(record['passage']):
        raise b.AppError('Passage offsets must identify its exact Unicode characters.')
    b.text_value(record['reviewer'], 'Reviewer label', 200, False)
    b.text_value(record['comment'], 'Reviewer comment', 20_000, False)
    for key in ('planned_text', 'revised_text', 'response'):
        b.text_value(record[key], key.replace('_', ' ').capitalize(), 40_000)
    if not isinstance(record['status'], str) or record['status'] not in STATUSES:
        raise b.AppError('Choose open, planned, revised or responded status.')
    if type(record['archived']) is not bool:
        raise b.AppError('Archived must be true or false.')
    if record['status'] == 'revised' and not record['revised_text'].strip():
        raise b.AppError('Record revised wording before marking a comment revised.')
    if record['status'] == 'responded' and not record['response'].strip():
        raise b.AppError('Record a response before marking a comment responded.')


def _record_fields(record, version):
    _keys(record, RECORD_FIELDS, 'Reviewer record', RECORD_FIELDS)
    for key in ('id', 'note_id'):
        b.identifier(record[key])
    for key in ('created_at', 'updated_at'):
        b.text_value(record[key], 'Reviewer record date', 100, False)
    _snapshot_fields(record)
    history = record['history']
    if not isinstance(history, list) or len(history) > HISTORY_LIMIT:
        raise b.AppError('A reviewer comment supports 200 retained changes. Existing history was retained.', 413)
    previous = 0
    for entry in history:
        _keys(entry, HISTORY_FIELDS, 'Reviewer history', HISTORY_FIELDS)
        _snapshot_fields(entry)
        b.text_value(entry['replaced_at'], 'Reviewer change date', 100, False)
        _integer(entry['reviewer_version'], 'Reviewer change version', 1, version)
        if entry['reviewer_version'] <= previous:
            raise b.AppError('Reviewer history versions must increase.')
        previous = entry['reviewer_version']


def validate_backup(state, workspace_id, notes):
    """Reject malformed identities/history before restore creates any workspace."""
    if state is None:
        return _default(workspace_id)
    _keys(state, STATE_FIELDS, 'Backup reviewer state', STATE_FIELDS)
    if type(state['schema_version']) is not int or state['schema_version'] != 1 or state['workspace_id'] != workspace_id:
        raise b.AppError('Backup reviewer schema or workspace is invalid.')
    _integer(state['version'], 'Reviewer version')
    if len(json.dumps(state, ensure_ascii=False).encode('utf-8')) > STATE_LIMIT:
        raise b.AppError('Reviewer state exceeds its 4 MB limit.', 413)
    if not isinstance(state['comments'], list) or len(state['comments']) > RECORD_LIMIT:
        raise b.AppError('Reviewer workspace supports at most 1,000 comments.', 413)
    indexed = {note['id']: note for note in notes}
    seen = set(indexed)
    for record in state['comments']:
        _record_fields(record, state['version'])
        if record['id'] in seen:
            raise b.AppError('Reviewer identity is duplicated or conflicts with a manuscript.')
        seen.add(record['id'])
        note = indexed.get(record['note_id'])
        if note is None:
            raise b.AppError('Reviewer comment references a missing manuscript.')
        for snapshot in [record] + record['history']:
            if snapshot['note_version'] > note['version']:
                raise b.AppError('Reviewer passage version is newer than the saved manuscript.')
            if snapshot['note_version'] == note['version'] and note['body'][snapshot['passage_start']:snapshot['passage_end']] != snapshot['passage']:
                raise b.AppError('Reviewer passage does not match its saved manuscript version.')
    return copy.deepcopy(state)


def remap_backup(state, workspace_id, mapping, remap_refs, original_notes=None):
    """Rebuild current anchors from whole remapped writing, including partial markers.

    Older snapshots retain their historical wording when that note version is
    unavailable. Their different note version continues to signal staleness.
    """
    result = copy.deepcopy(state)
    result['workspace_id'] = workspace_id
    notes = {note['id']: note for note in original_notes or []}
    for record in result['comments']:
        original_note = notes.get(record['note_id'])
        remapped_body = remap_refs(original_note['body']) if original_note is not None else None
        record['id'] = b.new_id()
        record['note_id'] = mapping[record['note_id']]
        for snapshot in [record] + record['history']:
            if original_note is not None and snapshot['note_version'] == original_note['version']:
                snapshot['passage'] = remapped_body[snapshot['passage_start']:snapshot['passage_end']]
            else:
                snapshot['passage'] = remap_refs(snapshot['passage'])
            for field in ('comment', 'planned_text', 'revised_text', 'response'):
                snapshot[field] = remap_refs(snapshot[field])
    return result


class Reviewer:
    def __init__(self, store):
        self.store = store

    @staticmethod
    def supports(method, route):
        return method == 'GET' and route == '/api/reviewer' or method == 'POST' and route in {'/api/reviewer/comment', '/api/reviewer/export'}

    @staticmethod
    def key(workspace_id):
        return 'reviewer:v1:' + workspace_id

    def load(self, workspace_id):
        self.store._workspace(workspace_id)
        row = self.store.db.execute('SELECT value FROM settings WHERE key=?', (self.key(workspace_id),)).fetchone()
        return json.loads(row[0]) if row else _default(workspace_id)

    def save(self, state):
        if len(json.dumps(state, ensure_ascii=False).encode('utf-8')) > STATE_LIMIT:
            raise b.AppError('Reviewer state exceeds its 4 MB limit. Existing records were retained.', 413)
        if len(state['comments']) > RECORD_LIMIT:
            raise b.AppError('Reviewer workspace supports at most 1,000 comments. Existing records were retained.', 413)
        self.store.db.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (self.key(state['workspace_id']), json.dumps(state, ensure_ascii=False)))

    def _note(self, note_id, workspace_id):
        b.identifier(note_id)
        note = self.store.db.execute('SELECT * FROM notes WHERE id=? AND workspace_id=?', (note_id, workspace_id)).fetchone()
        if note is None:
            raise b.AppError('Saved manuscript not found in this workspace.', 404)
        return dict(note)

    def _anchor(self, record, workspace_id):
        note = self._note(record['note_id'], workspace_id)
        if record['note_version'] != note['version']:
            raise b.AppError('The saved manuscript changed. Save or reload it before linking this passage.', 409)
        if note['body'][record['passage_start']:record['passage_end']] != record['passage']:
            raise b.AppError('Select the exact passage at its saved manuscript position.')

    def public(self, state):
        result = copy.deepcopy(state)
        for record in result['comments']:
            reasons = []
            record['current_note_version'] = None
            record['revised_verification'] = 'not_recorded' if not record['revised_text'].strip() else 'manuscript_unavailable'
            try:
                note = self._note(record['note_id'], state['workspace_id'])
            except b.AppError:
                reasons.append('manuscript_unavailable')
            else:
                record['current_note_version'] = note['version']
                if record['revised_text'].strip():
                    record['revised_verification'] = 'exact_text_present' if record['revised_text'] in note['body'] else 'not_present'
                if note['version'] != record['note_version']:
                    reasons.append('note_version_changed')
                if note['body'][record['passage_start']:record['passage_end']] != record['passage']:
                    reasons.append('passage_changed')
            record['stale'] = bool(reasons)
            record['stale_reasons'] = reasons
        return result

    def dispatch(self, method, route, payload):
        if method == 'GET':
            _keys(payload, {'workspace_id'}, 'Reviewer request', {'workspace_id'})
            return self.public(self.load(payload['workspace_id']))
        allowed = {'workspace_id', 'expected_version'}
        fields = {'title', 'include_archived'} if route.endswith('/export') else SNAPSHOT_FIELDS | {'id', 'note_id'}
        _keys(payload, allowed | fields, 'Reviewer write', allowed)
        _integer(payload['expected_version'], 'Expected reviewer version')
        state = self.load(payload['workspace_id'])
        if payload['expected_version'] != state['version']:
            raise b.AppError('Reviewer records changed in another window. Refresh records; your pending fields are retained.', 409)
        if route.endswith('/export'):
            return self.export(state, payload)
        changes = {key: value for key, value in payload.items() if key not in allowed}
        previous = copy.deepcopy(state)
        stamp = b.now()
        if 'id' in changes:
            b.identifier(changes['id'])
            record = next((row for row in state['comments'] if row['id'] == changes['id']), None)
            if record is None:
                raise b.AppError('Reviewer comment not found in this workspace.', 404)
            _keys(changes, SNAPSHOT_FIELDS | {'id'}, 'Reviewer comment update')
            if ANCHOR_FIELDS & set(changes) and not ANCHOR_FIELDS <= set(changes):
                raise b.AppError('Explicit relinking requires the saved version, both offsets and exact passage together.')
            candidate = {**record, **changes}
            _snapshot_fields(candidate)
            if ANCHOR_FIELDS & set(changes):
                self._anchor(candidate, state['workspace_id'])
            if any(record[key] != candidate[key] for key in SNAPSHOT_FIELDS):
                candidate['history'] = record['history'] + [{**{key: record[key] for key in SNAPSHOT_FIELDS}, 'replaced_at': stamp, 'reviewer_version': state['version'] + 1}]
                candidate['updated_at'] = stamp
                record.update(candidate)
        else:
            required = ANCHOR_FIELDS | {'note_id', 'reviewer', 'comment'}
            _keys(changes, SNAPSHOT_FIELDS | {'note_id'}, 'Reviewer comment creation', required)
            record = {'id': b.new_id(), 'planned_text': '', 'revised_text': '', 'response': '', 'status': 'open', 'archived': False,
                      'created_at': stamp, 'updated_at': stamp, 'history': [], **changes}
            _snapshot_fields(record)
            self._anchor(record, state['workspace_id'])
            state['comments'].append(record)
        if state == previous:
            return self.public(state)
        if state['version'] >= 1_000_000:
            raise b.AppError('Reviewer version limit reached. Existing records were retained.', 409)
        state['version'] += 1
        _record_fields(record, state['version'])
        with self.store.db:
            self.save(state)
        return self.public(state)

    def export(self, state, payload):
        title = b.text_value(payload.get('title', 'Response to reviewers'), 'Response letter title', 400, False)
        include = payload.get('include_archived', False)
        if type(include) is not bool:
            raise b.AppError('Include archived must be true or false.')
        rows = [row for row in self.public(state)['comments'] if include or not row['archived']]
        lines = [title, '', 'Saved reviewer record version: ' + str(state['version']),
                 'Prepared from saved local records. Review all wording and manuscript changes before sharing.', '']
        if not rows:
            lines.append('No reviewer comments are included.')
        for index, row in enumerate(rows, 1):
            note = self._note(row['note_id'], state['workspace_id'])
            revised_check = {'not_recorded': 'No revised wording recorded.',
                             'not_present': 'Recorded revised wording is absent from the current saved manuscript.',
                             'manuscript_unavailable': 'Current saved manuscript is unavailable; revised wording is unverified.',
                             'exact_text_present': 'Exact revised wording is present in current saved manuscript version ' + str(row['current_note_version']) + '; confirm location and context manually.'}[row['revised_verification']]
            lines.extend([str(index) + '. ' + row['reviewer'], 'Status: ' + row['status'] + (' | STALE manuscript link: relink or review required' if row['stale'] else '') + (' | archived' if row['archived'] else ''),
                          'Manuscript: ' + (note['title'] or 'Untitled note') + ' | linked saved version ' + str(row['note_version']),
                          'Comment:', row['comment'], '', 'Response:', row['response'] or '[Response pending]', '',
                          'Linked manuscript passage:', row['passage'], '', 'Planned wording / action:', row['planned_text'] or '[Not recorded]', '',
                          'Revised wording (record only; confirm manuscript separately):', row['revised_text'] or '[Not recorded]', '',
                          'Revised wording check: ' + revised_check, '',
                          str(len(row['history'])) + ' retained earlier record' + ('s' if len(row['history']) != 1 else '') + '; last saved ' + row['updated_at'], '', '---', ''])
        return {'filename': 'reviewer-response.txt', 'content': '\n'.join(lines), 'record_version': state['version'], 'count': len(rows),
                'notice': 'Saved records exported. Planned/revised wording does not change or verify the manuscript.'}
