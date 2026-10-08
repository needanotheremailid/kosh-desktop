"""Opt-in, offline benchmark using invented nonclinical data in a NEW directory.

Run from the source root: python scripts/benchmark_local.py --output NEW_FOLDER
This does not read an existing library or contact a provider.
"""
import argparse
import base64
import ctypes
import hashlib
import json
from pathlib import Path
import random
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import Store, pdf_lib


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--documents', type=int, default=256)
    parser.add_argument('--payload-mib', type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.documents <= 1000 or not 0 <= args.payload_mib <= 25:
        parser.error('Use 1–1000 documents and 0–25 MiB payload per document.')
    args.output.mkdir(parents=True, exist_ok=False)
    result = {'fixture': 'Invented nonclinical PDFs and text; no user library',
              'documents': args.documents, 'pages_per_document': 4,
              'payload_mib_per_document': args.payload_mib, 'notes': 50,
              'note_characters': 60000, 'historical_revisions': 250,
              'timings_seconds': {}, 'limits': 'Single Windows run; not a capacity guarantee or UI latency measurement.'}
    timings = result['timings_seconds']
    store = Store(args.output / 'data')
    try:
        work = store.dispatch('POST', '/api/workspaces', {'title': 'Reading methods bench'})['id']
        imported_hashes = []
        started = time.perf_counter()
        for index in range(args.documents):
            with pdf_lib.open() as document:
                for page_index in range(4):
                    page = document.new_page()
                    page.insert_text((42, 60), 'Reading methods %s, page %s. Spaced recall and desk organization.' % (index, page_index + 1))
                if args.payload_mib:
                    document.embfile_add('fixture.bin', random.Random(index).randbytes(args.payload_mib * 1024 * 1024))
                original = document.tobytes()
            row = store.dispatch('POST', '/api/import', {'workspace_id': work, 'files': [
                {'name': 'reading-%04d.pdf' % index, 'data': base64.b64encode(original).decode('ascii')}]})['results'][0]
            assert row['status'] == 'ready', row['status']
            imported_hashes.append(hashlib.sha256(original).hexdigest())
        timings['generate_and_import'] = round(time.perf_counter() - started, 3)
        started = time.perf_counter()
        body = ('Recall improves when the reader returns to a source and writes a short note.\n\n' * 1000)[:60000]
        for index in range(50):
            note = store.dispatch('POST', '/api/notes', {'workspace_id': work, 'title': 'Reading draft %02d' % index, 'body': body})
            for revision in range(5):
                note = store.dispatch('POST', '/api/notes', {'workspace_id': work, 'id': note['id'], 'title': note['title'],
                    'version': note['version'], 'body': body + '\nRevision ' + str(revision + 1)})
        timings['create_notes_and_revisions'] = round(time.perf_counter() - started, 3)
        for label, operation in (
            ('workspace_state', lambda: store.dispatch('GET', '/api/state?workspace_id=' + work)),
            ('passage_search', lambda: store.dispatch('POST', '/api/search', {'workspace_id': work, 'query': 'spaced recall'}))):
            readings = []
            for _ in range(5):
                started = time.perf_counter(); value = operation(); readings.append(time.perf_counter() - started)
            timings[label] = {'median': round(statistics.median(readings), 4), 'max': round(max(readings), 4), 'runs': 5}
            if label == 'workspace_state':
                result['state_json_bytes'] = len(json.dumps(value).encode())
        archive = args.output / 'workspace.zip'
        started = time.perf_counter(); saved = store.write_backup(work, archive)
        timings['backup'] = round(time.perf_counter() - started, 3)
        result['archive_bytes'] = saved['bytes']
        started = time.perf_counter(); preview = store.restore_backup_file(archive, preview_only=True)
        timings['preview'] = round(time.perf_counter() - started, 3)
        assert preview['documents'] == args.documents and preview['notes'] == 50 and preview['revisions'] == 250
        started = time.perf_counter(); restored = store.restore_backup_file(archive)
        timings['restore'] = round(time.perf_counter() - started, 3)
        state = store.dispatch('GET', '/api/state?workspace_id=' + restored['workspace_id'])
        assert sorted(row['sha256'] for row in state['documents']) == sorted(imported_hashes)
        assert len(state['notes']) == 50 and all(row['version'] == 6 for row in state['notes'])
        assert store.db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        result['verified'] = ['all original SHA256 values', 'document/note/history counts', 'saved note versions', 'SQLite integrity']
        result['ok'] = True
    finally:
        store.close()
    (args.output / 'benchmark.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
