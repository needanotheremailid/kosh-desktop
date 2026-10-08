"""Check a fresh installed package with synthetic inputs and no provider calls."""
import argparse
import base64
import hashlib
import io
import json
import random
from pathlib import Path
import sys
import tempfile
import time
import zipfile


def check_next_workflows(store, temporary, installed):
    from updater import Updater
    workspace = store.dispatch('POST', '/api/workspaces', {'title':'Review release check'})['id']
    note = store.dispatch('POST', '/api/notes', {'workspace_id':workspace,'title':'Widget draft','body':'Widgets are blue.'})
    reviewed = store.dispatch('POST', '/api/reviewer/comment', {'workspace_id':workspace,'expected_version':0,
        'note_id':note['id'],'note_version':1,'passage_start':0,'passage_end':17,'passage':'Widgets are blue.',
        'reviewer':'Reviewer 1','comment':'Explain the comparison.','response':'Comparison will be clarified.','status':'responded'})
    assert len(reviewed['comments']) == 1 and not reviewed['comments'][0]['stale']
    letter = store.dispatch('POST', '/api/reviewer/export', {'workspace_id':workspace,'expected_version':1})
    assert 'Comparison will be clarified.' in letter['content'] and letter['count'] == 1
    dashboard = store.dispatch('GET', '/api/project-review?workspace_id='+workspace)
    assert dashboard['totals']['drafts'] == 1 and dashboard['totals']['drafts_without_reviews'] == 1
    destination = Path(temporary)/'backups'; destination.mkdir()
    backups = store.auto_backups
    backups.build = manifest['build']
    backups.configure({'enabled':True,'destination':str(destination),'interval_minutes':1440})
    saved = backups.run_now()
    assert saved['ok'] and backups.status()['last_success']
    preview = backups.preview_restore({'set_id':saved['set_id'],'workspace_id':workspace})
    assert preview['reviewer_comments'] == 1 and preview['notes'] == 1
    restored = backups.restore({'preview_id':preview['preview_id'],'approve':True})
    result = store.dispatch('GET','/api/reviewer?workspace_id='+restored['workspace_id'])
    assert result['comments'][0]['note_id'] != note['id'] and not result['comments'][0]['stale']
    updates = Updater(installed,cache_dir=Path(temporary)/'updates')
    status = updates.status()
    assert status['current_version'] == '1.0.0-rc.3' and status['phase'] == 'idle' and status['signature'] == 'not_verified'
    return {'reviewer_letter':True,'dashboard':True,'automatic_backup_restore':True,'update_status_no_network':True}


def check_large_backup_and_revisions(store, temporary):
    workspace = store.dispatch('POST', '/api/workspaces', {'title':'Archive release check'})['id']
    hashes = []
    for index in range(2):
        with pymupdf.open() as document:
            document.new_page().insert_text((40, 50), 'Invented archive source ' + str(index))
            document.embfile_add('example.bin', random.Random(index).randbytes(25 * 1024 * 1024))
            original = document.tobytes()
        result = store.dispatch('POST', '/api/import', {'workspace_id':workspace, 'files':[
            {'name':'archive-' + str(index) + '.pdf', 'data':base64.b64encode(original).decode('ascii')}]})['results'][0]
        assert result['status'] == 'ready'
        hashes.append(hashlib.sha256(original).hexdigest())
    note = store.dispatch('POST', '/api/notes', {'workspace_id':workspace, 'title':'Saved draft', 'body':'Before\n'})
    changed = store.dispatch('POST', '/api/notes', {'workspace_id':workspace, 'id':note['id'],
        'version':1, 'title':'Revised draft', 'body':'After\n'})
    query = '/api/notes/history?id=' + note['id'] + '&workspace_id=' + workspace + '&expected_version=2'
    metadata = store.dispatch('GET', query + '&metadata_only=1')
    assert [row['version'] for row in metadata['revisions']] == [2,1]
    assert all('body' not in row for row in metadata['revisions'])
    assert store.dispatch('GET', query + '&version=1')['revisions'][0]['body'] == 'Before\n'
    assert store.dispatch('GET', query + '&version=2')['revisions'][0]['body'] == changed['body']
    archive = Path(temporary) / 'large-workspace.zip'
    def wait_job(body):
        job = store.auto_backups.start_job(body)
        deadline = time.monotonic() + 120
        while job['state'] in {'queued', 'running'}:
            assert time.monotonic() < deadline, 'Local backup job timed out.'
            time.sleep(0.05)
            job = store.auto_backups.job_status(job['job_id'])
        assert job['state'] == 'complete', job.get('error')
        return job['result']
    receipt = wait_job({'operation':'backup', 'workspace_id':workspace,
                        'path':str(archive), 'include_history':True})
    assert receipt['bytes'] > 47 * 1024 * 1024
    preview = wait_job({'operation':'preview', 'path':str(archive)})
    assert preview['documents'] == 2 and preview['revisions'] == 1
    restored = store.auto_backups.restore_local({'preview_id':preview['preview_id'], 'approve':True})
    state = store.dispatch('GET', '/api/state?workspace_id=' + restored['workspace_id'])
    assert sorted(row['sha256'] for row in state['documents']) == sorted(hashes)
    assert state['notes'][0]['body'] == changed['body'] and state['notes'][0]['version'] == 2
    return {'archive_bytes':receipt['bytes'], 'original_hashes_preserved':True,
            'saved_revision_metadata_and_bodies':True, 'fresh_workspace_restore':True}


def check_reading_workflow(store):
    """Exercise persisted reading records and restored identities in a temp store."""
    workspace = store.dispatch('POST', '/api/workspaces', {'title': 'Synthetic reading release check'})['id']
    with pymupdf.open() as document:
        document.new_page().insert_text((40, 50), 'Synthetic widgets have wheels.')
        document.new_page().insert_text((40, 50), 'Synthetic wheels have spokes.')
        original = document.tobytes()
    source = store.dispatch('POST', '/api/import', {'workspace_id': workspace, 'files': [
        {'name': 'synthetic-reading.pdf', 'data': base64.b64encode(original).decode('ascii')}
    ]})['results'][0]['document']
    source_id = source['id']
    assert source['sha256'] == hashlib.sha256(original).hexdigest()
    assert source['pages'] == 2
    assert store.file_response('/api/file', {'id': source_id})[0] == original
    note = store.dispatch('POST', '/api/notes', {'workspace_id': workspace, 'title': 'Synthetic claim',
        'body': 'Synthetic wheels have spokes. [[source:' + source_id + ':2]]'})

    def current(workspace_id=workspace):
        return store.dispatch('GET', '/api/reading?workspace_id=' + workspace_id)

    def save(operation, **fields):
        return store.dispatch('POST', '/api/reading/' + operation, {
            'workspace_id': workspace, 'expected_version': current()['version'], **fields})

    save('source', document_id=source_id, tags=['release-check'], collection='Methods',
         status='reading', favorite=True, last_page=2)
    save('resume', document_id=source_id, page=2, note_id=note['id'], view='write',
         panel='notes', next_action='Return to the synthetic spokes claim')
    geometry = store.dispatch('GET', '/api/reading/geometry?workspace_id=' + workspace +
        '&document_id=' + source_id + '&page=2')
    assert [word['text'] for word in geometry['words']] == ['Synthetic', 'wheels', 'have', 'spokes.']
    indices = [0, 1, 2, 3]
    annotation = save('annotation', document_id=source_id, page=2,
        quote='Synthetic wheels have spokes.', word_indices=indices,
        comment='Synthetic annotation only', color='yellow')['annotations'][0]
    assert annotation['rects'] == [word['rect'] for word in geometry['words']]
    assert all(0 <= coordinate <= 1 for rect in annotation['rects'] for coordinate in rect)
    archived = save('annotation', id=annotation['id'], archived=True)['annotations'][0]
    assert archived['archived'] and archived['quote'] == 'Synthetic wheels have spokes.'
    save('annotation', id=annotation['id'], archived=False)
    claim = save('claim', note_id=note['id'], note_version=1,
        claim_anchor='Synthetic wheels have spokes.', status='attached', document_id=source_id,
        page=2, excerpt='Synthetic wheels have spokes.')['claims'][0]
    checked = save('claim', id=claim['id'], status='checked')['claims'][0]
    assert checked['status'] == 'checked' and checked['stale'] is False
    changed_note = store.dispatch('POST', '/api/notes', {'workspace_id': workspace,
        'id': note['id'], 'version': 1, 'title': 'Synthetic claim',
        'body': 'Synthetic wheels might have spokes. [[source:' + source_id + ':2]]'})
    stale = current()['claims'][0]
    assert stale['status'] == 'checked' and stale['stale']
    assert 'note_version_changed' in stale['stale_reasons']
    try:
        save('claim', id=claim['id'], status='checked')
    except backend.AppError as error:
        assert error.status == 409
    else:
        raise AssertionError('A stale claim was marked checked.')
    before = current()
    backup = store.file_response('/api/backup', {'workspace_id': workspace, 'history': '0'})[0]
    restored_workspace = store.dispatch('POST', '/api/restore', {
        'data': base64.b64encode(backup).decode('ascii')})['workspace_id']
    assert restored_workspace != workspace
    restored = current(restored_workspace)
    restored_source = restored['sources'][0]['document_id']
    restored_note = restored['resume']['note_id']
    assert restored_source != source_id and restored_note != note['id']
    assert restored['resume']['document_id'] == restored_source and restored['resume']['page'] == 2
    assert restored['resume']['next_action'] == 'Return to the synthetic spokes claim'
    assert restored['sources'][0] == {**before['sources'][0], 'document_id': restored_source}
    assert restored['annotations'][0]['id'] != annotation['id']
    assert restored['annotations'][0]['document_id'] == restored_source
    assert restored['annotations'][0]['quote'] == annotation['quote']
    assert restored['annotations'][0]['rects'] == annotation['rects']
    assert restored['annotations'][0]['archived'] is False
    assert restored['claims'][0]['id'] != claim['id']
    assert restored['claims'][0]['note_id'] == restored_note
    assert restored['claims'][0]['document_id'] == restored_source
    assert restored['claims'][0]['note_version'] == 1 and restored['claims'][0]['status'] == 'checked'
    assert restored['claims'][0]['stale'] and 'note_version_changed' in restored['claims'][0]['stale_reasons']
    restored_state = store.dispatch('GET', '/api/state?workspace_id=' + restored_workspace)
    assert restored_state['notes'][0]['version'] == changed_note['version']
    assert '[[source:' + restored_source + ':2]]' in restored_state['notes'][0]['body']
    assert store.file_response('/api/file', {'id': restored_source})[0] == original
    assert store.file_response('/api/file', {'id': source_id})[0] == original
    assert current() == before, 'Restore changed the original workspace reading records.'
    return {'source_pages': 2, 'annotations': 1, 'claims': 1,
            'stale_check_rejected': True, 'backup_restore_ids': True, 'originals_preserved': True}


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--install-dir', type=Path, required=True)
args = parser.parse_args()
root = args.install_dir.resolve()
assert Path(sys.executable).resolve().is_relative_to(root / 'runtime')
assert sys.flags.ignore_environment and sys.flags.no_user_site
assert not (root / 'data').exists(), 'Use a fresh unlaunched installation.'
manifest = json.loads((root / 'package-manifest.json').read_text(encoding='utf-8-sig'))
for row in manifest['files']:
    path = (root / row['path']).resolve()
    assert path.is_relative_to(root) and path.is_file()
    assert path.stat().st_size == row['size']
    assert hashlib.sha256(path.read_bytes()).hexdigest() == row['sha256'], row['path']
sys.path.insert(0, str(root))
import backend, csl_engine, csl_styles, manuscript, manuscript_templates, reading, tex_compile, word_citations
from installation_health import check as installation_check
diagnostics = installation_check(root, app_version='1.0.0-rc.3', app_build=manifest['build'])
assert all(row['status'] == 'available' for row in diagnostics['components'].values() if row['requirement'] == 'required')
import pymupdf, docx, lxml
for module in (backend, csl_engine, csl_styles, manuscript, manuscript_templates, reading,
               tex_compile, word_citations, pymupdf, docx, lxml):
    assert Path(module.__file__).resolve().is_relative_to(root), module.__name__
with tempfile.TemporaryDirectory(prefix='kosh-release-smoke-') as temporary:
    store = backend.Store(Path(temporary) / 'data')
    try:
        assert store.dispatch('GET', '/api/workspaces', {})['workspaces'] == []
        reading_checks = check_reading_workflow(store)
        next_checks = check_next_workflows(store, temporary, root)
        large_checks = check_large_backup_and_revisions(store, temporary)
    finally:
        store.close()
    library = csl_styles.StyleLibrary(Path(temporary) / 'styles')
    assert len(library.list_locales()) == 63
    bundle = library.resolve_bundle('chicago-note')
    item = {'id':'a','type':'book','title':'Synthetic widgets','author':[{'family':'Doe','given':'Jane'}], 'issued':{'date-parts':[[2024]]}}
    formatted = csl_engine.render([item], [['a']], **{key:bundle[key] for key in ('style_xml','language','locales')})
    assert formatted['style_class'] == 'note' and 'synthetic widgets' in formatted['citations'][0].casefold()
markdown = '# Synthetic release check\n\n## Findings\n\n'+r'$$\begin{pmatrix}1 & 2\\3 & 4\end{pmatrix}\quad\int_0^1x^2\,dx=\frac13,\quad\mathbb{R}+\mathfrak{g}$$'
options = manuscript_templates.validate_template({'profile':'research','authors':'Synthetic Author'})
markdown = manuscript_templates.template_markdown(markdown, options, 'Synthetic release check')
protected, equations = tex_compile.prepare_math(markdown)
tex = tex_compile.restore_math(manuscript.render_latex(protected), equations)
tex = manuscript_templates.apply_tex_template(tex, options, 'Synthetic release check')
pdf = tex_compile.compile_tex(tex)
with pymupdf.open(stream=pdf, filetype='pdf') as document:
    text = '\n'.join(page.get_text() for page in document)
    assert 'Synthetic release check' in text and len(document) >= 2
    pages = len(document)
sys.path.insert(0, str(root / 'tests'))
from test_exports_completion import FakeStore, query
from exports import export_workspace
chicago_pdf, chicago_mime, _ = export_workspace(
    FakeStore(), query('pdf', citation_style='chicago-note', note_placement='footnote'))
assert chicago_mime == 'application/pdf'
with pymupdf.open(stream=chicago_pdf, filetype='pdf') as document:
    chicago_text = '\n'.join(page.get_text() for page in document)
    assert 'Widgets' in chicago_text and 'Doe' in chicago_text
    chicago_pages = len(document)
source = {'id':'a'*32,'kind':'pdf','pages':1,'name':'synthetic.pdf',
          'metadata':{'type':'journal_article','title':'Synthetic widgets','year':'2024'}}
word = word_citations.render_live_docx('Claim [[source:'+'a'*32+':1]].', [source])
with zipfile.ZipFile(io.BytesIO(word)) as archive:
    assert b'CITATION' in archive.read('word/document.xml')
    assert b'BIBLIOGRAPHY' in archive.read('word/document.xml')
    assert b'Synthetic widgets' in archive.read('customXml/item1.xml')
print(json.dumps({'ok':True,'build':manifest['build'],'verified_payload_files':len(manifest['files']),
                  'bundled_origins':True,'empty_library':True,'csl_locales':63,
                  'reading_workflow':reading_checks,
                  'next_workflows':next_checks,
                  'large_backup_and_revisions':large_checks,
                  'installation_health':diagnostics,
                  'offline_compiled_pdf_pages':pages,'default_chicago_pdf_pages':chicago_pages,'native_word_fields':True,
                  'scope':'Fresh installed runtime checks; synthetic inputs; no desktop UI or native Word automation.'}))
