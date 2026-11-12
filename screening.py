"""Versioned, manual screening decisions kept in workspace settings."""
import copy
import json

import backend as b


STATE_LIMIT = 4 * 1024 * 1024
RECORD_LIMIT = 1000
HISTORY_LIMIT = 200
STAGES = {'title_abstract', 'full_text'}
DECISIONS = {'include', 'maybe', 'exclude'}


def _keys(value, fields, label):
    if not isinstance(value, dict) or set(value) != fields:
        raise b.AppError(label + ' has missing or unsupported fields.')


def _integer(value, label):
    if type(value) is not int or not 0 <= value <= 1_000_000:
        raise b.AppError(label + ' is outside its supported integer range.')


def _default(workspace_id):
    return {'workspace_id': workspace_id, 'version': 0,
            'criteria': {'include': [], 'exclude': []}, 'records': {}}


def _criteria(criteria):
    _keys(criteria, {'include', 'exclude'}, 'Screening criteria')
    for items in criteria.values():
        if not isinstance(items, list) or len(items) > 100:
            raise b.AppError('Each criteria list supports at most 100 items.')
        for item in items:
            b.text_value(item, 'Screening criterion', 2000, False)


def _decision(value, stage, history=False):
    fields = {'decision', 'reason', 'decided_at'}
    if history:
        fields |= {'stage', 'replaced_at'}
    _keys(value, fields, 'Screening decision')
    if not isinstance(value['decision'], str) or value['decision'] not in DECISIONS:
        raise b.AppError('Choose include, maybe or exclude.')
    b.text_value(value['reason'], 'Screening reason', 2000)
    b.text_value(value['decided_at'], 'Decision date', 100, False)
    if history:
        if not isinstance(value['stage'], str) or value['stage'] not in STAGES:
            raise b.AppError('Choose title_abstract or full_text stage.')
        stage = value['stage']
        b.text_value(value['replaced_at'], 'Replacement date', 100, False)
    if stage == 'full_text' and value['decision'] == 'exclude' and not value['reason'].strip():
        raise b.AppError('A reason is required when excluding at full text.')


def validate_backup(state, workspace_id, documents):
    if state is None:
        return _default(workspace_id)
    _keys(state, {'workspace_id', 'version', 'criteria', 'records'}, 'Screening state')
    b.identifier(state['workspace_id'])
    if state['workspace_id'] != workspace_id:
        raise b.AppError('Screening workspace is invalid.')
    _integer(state['version'], 'Screening version')
    _criteria(state['criteria'])
    records = state['records']
    if not isinstance(records, dict) or len(records) > RECORD_LIMIT:
        raise b.AppError('Screening supports at most 1,000 sources.', 413)
    ids = {row['id'] for row in documents}
    for document_id, record in records.items():
        b.identifier(document_id)
        if document_id not in ids:
            raise b.AppError('Screening record references a missing source.')
        _keys(record, {'title_abstract', 'full_text', 'history'}, 'Screening record')
        for stage in STAGES:
            if record[stage] is not None:
                _decision(record[stage], stage)
        if record['full_text'] is not None and (record['title_abstract'] is None or record['title_abstract']['decision'] not in {'include', 'maybe'}):
            raise b.AppError('Full-text decisions require an included or maybe title/abstract decision.')
        if not isinstance(record['history'], list) or len(record['history']) > HISTORY_LIMIT:
            raise b.AppError('A source supports at most 200 retained screening changes.', 413)
        for entry in record['history']:
            _decision(entry, None, history=True)
    if len(json.dumps(state, ensure_ascii=False).encode('utf-8')) > STATE_LIMIT:
        raise b.AppError('Screening state exceeds its 4 MB limit. Existing records were retained.', 413)
    return copy.deepcopy(state)


def remap_backup(state, workspace_id, mapping):
    result = copy.deepcopy(state)
    result['workspace_id'] = workspace_id
    result['records'] = {mapping[key]: value for key, value in result['records'].items()}
    return result


class Screening:
    def __init__(self, store):
        self.store = store

    @staticmethod
    def supports(method, route):
        return (method == 'GET' and route == '/api/screening' or
                method == 'POST' and route in {'/api/screening/decision', '/api/screening/criteria'})

    @staticmethod
    def key(workspace_id):
        return 'screening:v1:' + workspace_id

    def _documents(self, workspace_id):
        return [dict(row) for row in self.store.db.execute('SELECT id,archived FROM documents WHERE workspace_id=?', (workspace_id,))]

    def load(self, workspace_id):
        self.store._workspace(workspace_id)
        row = self.store.db.execute('SELECT value FROM settings WHERE key=?', (self.key(workspace_id),)).fetchone()
        if row is None:
            return _default(workspace_id)
        state = json.loads(row[0])
        if state is None:
            raise b.AppError('Saved screening state must be an object.')
        return validate_backup(state, workspace_id, self._documents(workspace_id))

    def save(self, state):
        validate_backup(state, state['workspace_id'], self._documents(state['workspace_id']))
        self.store.db.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                              (self.key(state['workspace_id']), json.dumps(state, ensure_ascii=False)))

    def public(self, state):
        flow = {'identified': 0, 'title_abstract_screened': 0, 'title_abstract_excluded': 0,
                'full_text_assessed': 0, 'full_text_excluded': 0, 'full_text_excluded_by_reason': {},
                'included': 0, 'undecided': 0}
        for document in self._documents(state['workspace_id']):
            if document['archived']:
                continue
            flow['identified'] += 1
            record = state['records'].get(document['id'], {})
            title = record.get('title_abstract')
            full = record.get('full_text')
            if title:
                flow['title_abstract_screened'] += 1
                if title['decision'] == 'exclude':
                    flow['title_abstract_excluded'] += 1
            if full:
                flow['full_text_assessed'] += 1
                if full['decision'] == 'exclude':
                    flow['full_text_excluded'] += 1
                    reason = full['reason'].strip()
                    flow['full_text_excluded_by_reason'][reason] = flow['full_text_excluded_by_reason'].get(reason, 0) + 1
                elif full['decision'] == 'include':
                    flow['included'] += 1
            if not (title and title['decision'] == 'exclude') and not (full and full['decision'] in {'include', 'exclude'}):
                flow['undecided'] += 1
        return {**copy.deepcopy(state), 'flow': flow}

    def dispatch(self, method, route, payload):
        if method == 'GET':
            _keys(payload, {'workspace_id'}, 'Screening request')
            return self.public(self.load(payload['workspace_id']))
        common = {'workspace_id', 'expected_version'}
        fields = {'criteria'} if route.endswith('/criteria') else {'document_id', 'stage', 'decision', 'reason'}
        _keys(payload, common | fields, 'Screening write')
        _integer(payload['expected_version'], 'Expected screening version')
        state = self.load(payload['workspace_id'])
        if payload['expected_version'] != state['version']:
            raise b.AppError('Screening records changed in another window. Refresh records; your pending fields are retained.', 409)
        previous = copy.deepcopy(state)
        if route.endswith('/criteria'):
            _criteria(payload['criteria'])
            state['criteria'] = copy.deepcopy(payload['criteria'])
        else:
            self.store._document(payload['document_id'], state['workspace_id'])
            stage = payload['stage']
            if not isinstance(stage, str) or stage not in STAGES:
                raise b.AppError('Choose title_abstract or full_text stage.')
            stamp = b.now()
            candidate = {'decision': payload['decision'], 'reason': payload['reason'], 'decided_at': stamp}
            _decision(candidate, stage)
            record = state['records'].setdefault(payload['document_id'], {'title_abstract': None, 'full_text': None, 'history': []})
            if stage == 'full_text' and (record['title_abstract'] is None or record['title_abstract']['decision'] not in {'include', 'maybe'}):
                raise b.AppError('Full-text decisions require an included or maybe title/abstract decision.')
            if stage == 'title_abstract' and candidate['decision'] == 'exclude' and record['full_text'] is not None:
                raise b.AppError('Cannot exclude at title/abstract while a full-text decision exists.')
            prior = record[stage]
            if prior and prior['decision'] == candidate['decision'] and prior['reason'] == candidate['reason']:
                return self.public(state)
            if prior:
                record['history'].append({'stage': stage, **prior, 'replaced_at': stamp})
            record[stage] = candidate
        if state == previous:
            return self.public(state)
        if state['version'] >= 1_000_000:
            raise b.AppError('Screening version limit reached. Existing records were retained.', 409)
        state['version'] += 1
        with self.store.db:
            self.save(state)
        return self.public(state)
