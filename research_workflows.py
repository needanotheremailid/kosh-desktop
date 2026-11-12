"""Local reading packets, saved-evidence comparisons and source-use reports.

These read saved records. They do not run an agent, fetch papers, conduct study
screening, calculate research results, or certify that a source supports a claim.
"""
import json
import re

from backend import AppError, now


SOURCE_LINK = re.compile(r'\[\[(?:source|reference):([a-f0-9]{32})(?::\d+)?\]\]')


def literal(value):
    """Keep imported/user text inert when composing Markdown rather than HTML."""
    return str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('[', '\\[').replace(']', '\\]')


def cell(value):
    return literal(value).replace('|', '\\|').replace('\r', '').replace('\n', ' / ')


def selected_documents(store, body, extra=()):
    if not isinstance(body, dict) or set(body) - {'workspace_id', 'document_ids', *extra}:
        raise AppError('Choose a workspace and explicit source IDs only.')
    workspace = store._workspace(body.get('workspace_id'))
    ids = body.get('document_ids')
    if not isinstance(ids, list) or not 1 <= len(ids) <= 10 or any(not isinstance(item, str) for item in ids) or len(set(ids)) != len(ids):
        raise AppError('Choose one to ten different sources in this workspace.')
    documents = [store._document(item, workspace['id']) for item in ids]
    for document in documents:
        if document['archived']:
            raise AppError('Unarchive the selected source before using it in a new research packet.', 409)
        store._bytes(document)
    return workspace, documents


def packet(store, body):
    workspace, documents = selected_documents(store, body, ('max_chars',))
    budget = body.get('max_chars', 24000)
    if type(budget) is not int or not 2000 <= budget <= 100000:
        raise AppError('Reading-packet text budget must be 2,000–100,000 characters.')
    sources, passages = [], []
    # Each selected source receives a visible, equal share. Large early files
    # cannot silently use the whole packet before a later source is represented.
    allowance = budget // len(documents)
    lines = ['# Reading packet', '', 'Workspace: ' + literal(workspace['title']),
             'Prepared: ' + now(), '', 'Exact extracted text only. Inclusion is not proof that a paper was fully read or a claim is supported.',
             'Extraction may omit images, equations or other content; inspect originals.', '']
    for document in documents:
        metadata_only = bool(document['metadata'].get('catalogue_source')) or document['kind'] in {'bib', 'ris'}
        unit_count, text_count = store.db.execute('SELECT count(*),coalesce(sum(length(text)),0) FROM pages WHERE document_id=?', (document['id'],)).fetchone()
        source = {'document_id': document['id'], 'name': document['name'], 'sha256': document['sha256'],
                  'units_total': unit_count, 'chars_total': text_count, 'chars_included': 0,
                  'chars_omitted': text_count, 'units_included': 0, 'coverage': 'no extracted text available',
                  'unit': 'file page' if document['kind'] == 'pdf' else 'text section',
                  'extraction_notice': document['extraction_notice']}
        lines += ['## ' + literal(document['metadata'].get('title') or document['name']),
                  'Source SHA-256: ' + document['sha256'], literal(document['extraction_notice'])]
        if metadata_only:
            source['coverage'] = 'catalogue metadata only'
            lines += ['', 'Catalogue metadata only. Import the paper to make a reading packet from its text.', '']
        else:
            remaining = allowance
            for page in store.db.execute('SELECT page,substr(text,1,?) AS text FROM pages WHERE document_id=? AND length(trim(text))>0 ORDER BY page', (allowance, document['id'])):
                if not remaining:
                    break
                text = page['text'][:remaining]
                if not text:
                    continue
                passages.append({'document_id': document['id'], 'name': document['name'], 'page': page['page'], 'text': text})
                remaining -= len(text)
                source['chars_included'] += len(text)
                source['units_included'] += 1
                lines += ['', '### ' + source['unit'].capitalize() + ' ' + str(page['page']) + ' [[source:' + document['id'] + ':' + str(page['page']) + ']]',
                          '', *['> ' + literal(line) for line in text.split('\n')]]
            source['chars_omitted'] = text_count - source['chars_included']
            if source['chars_included']:
                source['coverage'] = 'partial extracted text' if source['chars_omitted'] else 'all extracted text included'
            lines += ['', '**Coverage: ' + source['coverage'] + '** — ' + str(source['chars_included']) + ' of ' + str(text_count) + ' extracted characters.']
            if source['chars_omitted']:
                lines += ['TRUNCATED / OMITTED: ' + str(source['chars_omitted']) + ' characters are outside this packet. Increase the budget or choose fewer sources.']
            lines += ['']
        sources.append(source)
    markdown = '\n'.join(lines)
    if len(markdown) > 180000:
        raise AppError('Escaped reading packet exceeds the draft size limit. Choose a smaller text budget; no text was silently dropped.', 413)
    return {'workspace_id': workspace['id'], 'title': 'Reading packet', 'sources': sources, 'passages': passages,
            'max_chars': budget, 'markdown': markdown,
            'notice': 'Exact extracted text; not proof of complete-paper reading or scientific support. No AI or provider request was made.'}


def comparison(store, body):
    workspace, documents = selected_documents(store, body)
    rows = []
    lines = ['# Source comparison', '', 'Prepared: ' + now(), '',
             'Saved manual evidence only; not independently verified. Not recorded means no saved field, not absence in the paper.', '',
             '| Source | Question | Design | Findings | Limitations | Saved evidence |',
             '| --- | --- | --- | --- | --- | --- |']
    for document in documents:
        evidence = [dict(row) for row in store.db.execute('SELECT * FROM matrix WHERE workspace_id=? AND document_id=? ORDER BY id', (workspace['id'], document['id']))]
        # Show unassessed sources instead of quietly dropping them from synthesis.
        for item in evidence or [{}]:
            row = {'document_id': document['id'], 'name': document['metadata'].get('title') or document['name'],
                   'evidence_id': item.get('id'), 'evidence_version': item.get('version'),
                   **{key: item.get(key) or 'Not recorded' for key in ('question', 'design', 'findings', 'limitations')}}
            rows.append(row)
            lines.append('| ' + cell(row['name']) + ' [[reference:' + document['id'] + ']] | ' +
                         ' | '.join(cell(row[key]) for key in ('question', 'design', 'findings', 'limitations')) +
                         ' | ' + ('v' + str(row['evidence_version']) + ' · ' + row['evidence_id'] if row['evidence_id'] else 'No saved evidence row') + ' |')
    markdown = '\n'.join(lines)
    if len(markdown) > 180000:
        raise AppError('Comparison is too large for a draft. Choose fewer sources; no rows were silently dropped.', 413)
    return {'workspace_id': workspace['id'], 'title': 'Source comparison', 'rows': rows, 'markdown': markdown,
            'notice': 'A snapshot of saved manual evidence, not independently verified study extraction. Review sources and blank fields before synthesis.'}


def overview(store, workspace_id):
    workspace = store._workspace(workspace_id)
    linked = {}
    for note in store.db.execute('SELECT id,title,version,body FROM notes WHERE workspace_id=? ORDER BY updated_at DESC,id', (workspace_id,)):
        for source_id in set(SOURCE_LINK.findall(note['body'])):
            linked.setdefault(source_id, []).append({key: note[key] for key in ('id', 'title', 'version')})
    sources = []
    for document in store.db.execute('SELECT id,name,metadata,kind,status,archived FROM documents WHERE workspace_id=? ORDER BY created_at,id', (workspace_id,)):
        metadata = json.loads(document['metadata'])
        units, text_units = store.db.execute('SELECT count(*),coalesce(sum(length(trim(text))>0),0) FROM pages WHERE document_id=?', (document['id'],)).fetchone()
        sources.append({'id': document['id'], 'name': metadata.get('title') or document['name'], 'kind': document['kind'],
                        'status': document['status'], 'archived': bool(document['archived']), 'units': units, 'text_units': text_units,
                        'metadata_only': bool(metadata.get('catalogue_source')) or document['kind'] in {'bib', 'ris'},
                        'linked_notes': linked.get(document['id'], []),
                        'evidence_rows': store.db.execute('SELECT count(*) FROM matrix WHERE workspace_id=? AND document_id=?', (workspace_id, document['id'])).fetchone()[0]})
    return {'workspace_id': workspace['id'], 'title': workspace['title'], 'sources': sources,
            'notice': 'Saved source links and extracted-text availability only. A linked draft or available text does not establish that a source has been read or a claim verified.'}


def search_record(result, workspace_id):
    lines = ['# Literature search record', '', 'Query: ' + literal(result['query']),
             'Index: ' + literal(result['provider']), 'Retrieved (UTC): ' + result['retrieved_at'],
             'Returned records: ' + str(len(result['results'])), '',
             'First bounded result page(s), not an exhaustive search or formal screening record. Catalogue metadata is not full-paper evidence.', '']
    if result.get('provider_totals') is not None:
        lines += ['## Totals reported separately by each index']
        lines += ['- ' + key + ': ' + str(value) for key, value in result['provider_totals'].items()]
        lines += ['Do not add these totals: indexes overlap and may count different records.']
    else:
        lines += ['Index-reported matches: ' + str(result['total'])]
    for error in result.get('errors', []):
        lines += ['Index failed: ' + literal(error['provider']) + ' — ' + literal(error['error'])]
    lines += ['', '## Returned records']
    for item in result['results']:
        lines += ['- ' + literal(item.get('title') or 'Title unavailable') + ' · ' + literal(item.get('year') or 'Year unavailable') +
                  ' · DOI: ' + literal(item.get('doi') or 'Not supplied') + ' · ' + literal(item.get('url') or 'No catalogue URL')]
    return {'workspace_id': workspace_id, 'title': 'Search record: ' + result['query'][:180], 'body': '\n'.join(lines)}
