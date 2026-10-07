"""Fetch only PG-approved OCR files and the official nomic-embed-text model.

Reruns preserve differing existing files. No other model, account, dependency,
source tree or app data is changed. Optional pull uses fixed local Ollama only.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
from urllib.parse import urlsplit, urlunsplit
from urllib.request import ProxyHandler, Request, build_opener


OCR = (
    ('tessdata/eng.traineddata', 'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/eng.traineddata'),
    ('tessdata/hin.traineddata', 'https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/main/hin.traineddata'),
    ('tessdata/pan.traineddata', 'https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/main/pan.traineddata'),
    ('licences/tessdata_fast_LICENSE.txt', 'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/LICENSE'),
    ('licences/tessdata_best_LICENSE.txt', 'https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/main/LICENSE'),
)
MODEL = 'nomic-embed-text:latest'
MODEL_PAGE = 'https://ollama.com/library/nomic-embed-text'
MANIFEST = 'https://registry.ollama.ai/v2/library/nomic-embed-text/manifests/latest'


def sha(path):
    checksum = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            checksum.update(chunk)
    return checksum.hexdigest()


def clean_url(value):
    parts = urlsplit(value)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, '', ''))


def publish(temporary, target):
    if target.exists():
        if sha(target) != sha(temporary):
            raise RuntimeError('Existing component differs; retained without overwrite: ' + target.name)
    else:
        os.link(temporary, target)
    temporary.unlink()


def fetch(root, relative, url, maximum):
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix='kosh-component-', dir=target.parent)
    temporary = Path(name)
    opener = build_opener()
    try:
        headers = {'User-Agent': 'Kosh local component setup', 'Accept': 'application/vnd.docker.distribution.manifest.v2+json' if url == MANIFEST else '*/*'}
        print('Fetching approved file: ' + relative, flush=True)
        with os.fdopen(descriptor, 'wb') as output, opener.open(Request(url, headers=headers), timeout=120) as response:
            size, checksum = 0, hashlib.sha256()
            for chunk in iter(lambda: response.read(1024 * 1024), b''):
                size += len(chunk)
                if size > maximum:
                    raise RuntimeError('Approved component exceeded its bounded size.')
                output.write(chunk)
                checksum.update(chunk)
            output.flush()
            os.fsync(output.fileno())
            receipt = {'path': relative, 'source': url, 'resolved_source_without_query': clean_url(response.url), 'bytes': size,
                       'sha256': checksum.hexdigest(), 'etag': response.headers.get('ETag'), 'last_modified': response.headers.get('Last-Modified')}
        publish(temporary, target)
        if sha(target) != receipt['sha256']:
            raise RuntimeError('Published component hash did not match.')
        print('Verified ' + relative + ': ' + str(size) + ' bytes SHA256 ' + receipt['sha256'], flush=True)
        return receipt
    finally:
        if temporary.exists():
            temporary.unlink()


def local(route, payload=None, timeout=120):
    raw = None if payload is None else json.dumps(payload).encode()
    request = Request('http://127.0.0.1:11434' + route, data=raw, headers={'Content-Type': 'application/json'})
    return build_opener(ProxyHandler({})).open(request, timeout=timeout)


def pull():
    previous, last_update = None, 0
    with local('/api/pull', {'model': MODEL, 'stream': True}) as response:
        while True:
            line = response.readline(64 * 1024 + 1)
            if not line:
                break
            if len(line) > 64 * 1024:
                raise RuntimeError('Ollama pull progress exceeded its bound.')
            item = json.loads(line)
            if item.get('error'):
                raise RuntimeError('Official model pull failed. No other model or fallback source was requested.')
            status = item.get('status', 'Pulling approved model')
            stamp = time.monotonic()
            if status != previous or stamp - last_update >= 5 or status == 'success':
                completed, total = item.get('completed', 0), item.get('total', 0)
                suffix = f' {completed:,}/{total:,} bytes' if total else ''
                print(status + suffix, flush=True)
                previous, last_update = status, stamp
            if status == 'success':
                return
    raise RuntimeError('Model pull ended without a success receipt.')


def model_files(root, manifest):
    model_root = Path(os.environ.get('OLLAMA_MODELS') or Path.home() / '.ollama' / 'models')
    installed_manifest = model_root / 'manifests' / 'registry.ollama.ai' / 'library' / 'nomic-embed-text' / 'latest'
    installed = json.loads(installed_manifest.read_text(encoding='utf-8'))
    if installed.get('config') != manifest.get('config') or installed.get('layers') != manifest.get('layers'):
        raise RuntimeError('Installed model manifest does not match the approved registry manifest.')
    records = []
    for entry in [manifest['config'], *manifest['layers']]:
        digest = entry.get('digest', '')
        if not re.fullmatch(r'sha256:[a-f0-9]{64}', digest) or type(entry.get('size')) is not int:
            raise RuntimeError('Official model manifest contains an unsupported blob descriptor.')
        source = model_root / 'blobs' / digest.replace(':', '-')
        if not source.is_file() or source.stat().st_size != entry['size'] or sha(source) != digest[7:]:
            raise RuntimeError('Installed approved model blob failed size or hash verification.')
        relative = 'ollama/blobs/' + digest.replace(':', '-')
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if sha(target) != digest[7:]:
                raise RuntimeError('Existing staged model blob differs and was retained.')
        else:
            with tempfile.NamedTemporaryFile(prefix='kosh-model-', dir=target.parent, delete=False) as temporary:
                temp_path = Path(temporary.name)
                with source.open('rb') as incoming:
                    shutil.copyfileobj(incoming, temporary, 1024 * 1024)
            publish(temp_path, target)
        records.append({'path': relative, 'source': 'https://registry.ollama.ai/v2/library/nomic-embed-text/blobs/' + digest,
                        'bytes': entry['size'], 'sha256': digest[7:], 'media_type': entry['mediaType']})
        print('Verified approved model blob: ' + str(entry['size']) + ' bytes ' + entry['mediaType'], flush=True)
        if 'license' in entry['mediaType']:
            licence = root / 'licences' / 'nomic_embed_text_LICENSE.txt'
            if licence.exists() and sha(licence) != digest[7:]:
                raise RuntimeError('Existing model licence differs and was retained.')
            if not licence.exists():
                shutil.copyfile(target, licence)
    return records


def smoke(root):
    """Retain one isolated synthetic store and receipts; never touch app data."""
    import base64
    import sys
    from unittest.mock import patch
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from backend import Store
    import retrieval
    from retrieval import Retrieval
    directory = Path(tempfile.mkdtemp(prefix='semantic-smoke-', dir=root))
    store = Store(directory / 'data')
    try:
        workspace = store.dispatch('POST', '/api/workspaces', {'title': 'Synthetic local component proof'})['id']
        texts = [('widgets.txt', 'A machine can perform its work more quickly after the mechanism is improved.'),
                 ('gardening.txt', 'A gardener plants roses in fertile soil and waters the flowers each morning.'),
                 ('astronomy.txt', 'Astronomers observe distant galaxies and measure the light from stars.')]
        imported = []
        for name, text in texts:
            imported.append(store._import({'workspace_id': workspace, 'files': [{'name': name, 'data': base64.b64encode(text.encode()).decode()}]})['results'][0]['document'])
        instance = Retrieval(store)
        query = 'Equipment operates faster following a design upgrade.'
        lexical = store._search({'workspace_id': workspace, 'query': query})
        indexed = instance.dispatch('POST', '/api/retrieval/index', {'workspace_id': workspace, 'model': MODEL})
        semantic = instance.dispatch('POST', '/api/retrieval/search', {'workspace_id': workspace, 'model': MODEL, 'query': query})
        dimension = store.db.execute('SELECT DISTINCT dimension FROM semantic_chunks WHERE model=?', (MODEL,)).fetchone()[0]
        record = {'model': MODEL, 'embedding_dimension': dimension, 'query': query, 'lexical_results': len(lexical),
                  'index': indexed, 'semantic_results': semantic['results'], 'expected_document_id': imported[0]['id'],
                  'paraphrase_ranked_first': bool(semantic['results']) and semantic['results'][0]['document_id'] == imported[0]['id'],
                  'synthetic_only': True, 'data_directory': str(directory / 'data')}
        # Render a generated text page into an image-only PDF, then OCR it using
        # the staged official English file instead of system language data.
        import pymupdf
        source = pymupdf.open()
        page = source.new_page(width=500, height=120)
        page.insert_text((30, 65), 'THIRTY SYNTHETIC WIDGETS', fontsize=20)
        image = page.get_pixmap(matrix=pymupdf.Matrix(2, 2)).tobytes('png')
        image_pdf = pymupdf.open()
        image_pdf.new_page(width=500, height=120).insert_image(pymupdf.Rect(0, 0, 500, 120), stream=image)
        original = image_pdf.tobytes()
        source.close()
        image_pdf.close()
        doc = store._import({'workspace_id': workspace, 'files': [{'name': 'synthetic image.pdf', 'data': base64.b64encode(original).decode()}]})['results'][0]['document']
        with patch.object(retrieval, 'BUNDLED_TESSDATA', root / 'tessdata'):
            ocr = instance.dispatch('POST', '/api/ocr', {'workspace_id': workspace, 'document_id': doc['id'], 'language': 'eng', 'pages': [1]})
        derivative = ocr['results'][0]['document']
        extracted = store.dispatch('GET', '/api/document?id=' + derivative['id'])['text_pages'][0]['text']
        record['bundled_ocr'] = {'language': 'eng', 'recognised_text': extracted, 'recognised_synthetic_phrase': 'SYNTHETIC WIDGETS' in extracted.upper(),
                                 'original_preserved': store._bytes(store._document(doc['id'])) == original,
                                 'source_document_id': doc['id'], 'derivative_document_id': derivative['id'], 'page_mapping': ocr['page_mapping']}
        record['capabilities_after_execution'] = instance.capabilities(store)
        record['verified_at'] = datetime.now(timezone.utc).isoformat()
        proof = directory / 'local-component-smoke.json'
        proof.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print('Actual local smoke: ' + str(proof), flush=True)
        print('Lexical matches: ' + str(len(lexical)) + '; semantic paraphrase ranked first: ' + str(record['paraphrase_ranked_first']) + '; dimension: ' + str(dimension), flush=True)
        print('Staged English OCR recognised phrase: ' + str(record['bundled_ocr']['recognised_synthetic_phrase']) + '; original preserved: ' + str(record['bundled_ocr']['original_preserved']), flush=True)
        if lexical or not record['paraphrase_ranked_first'] or not record['bundled_ocr']['recognised_synthetic_phrase'] or not record['bundled_ocr']['original_preserved']:
            raise RuntimeError('Synthetic smoke did not meet its fixed independent expectations; evidence was retained.')
        return record, proof
    finally:
        store.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--pull-model', action='store_true', help='Install only the user-approved official nomic-embed-text:latest model')
    parser.add_argument('--smoke-only', action='store_true', help='Run isolated synthetic local execution checks without fetching or pulling')
    args = parser.parse_args(argv)
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if args.smoke_only:
        record, proof = smoke(root)
        receipt_path = root / 'component-receipt.json'
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        receipt.pop('model_local_ready', None)
        receipt['model_embedding_capability_verified'] = 'embedding' in receipt.get('model_capabilities', [])
        receipt['model_runtime_verified'] = True
        receipt['model_embedding_dimension'] = record['embedding_dimension']
        receipt['synthetic_execution_receipt'] = str(proof.relative_to(root))
        receipt['verified_at'] = record['verified_at']
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return
    receipt = {'verified_at': datetime.now(timezone.utc).isoformat(), 'approved_files_only': True, 'files': [], 'model': MODEL,
               'notice': 'OCR language data and model files were fetched only from the approved official sources. Hashes verify captured bytes, not legal compliance certification. Other models were not downloaded or altered.'}
    for relative, url in OCR:
        receipt['files'].append(fetch(root, relative, url, 64 * 1024 * 1024))
    receipt['files'].append(fetch(root, 'ollama/model-page.html', MODEL_PAGE, 2 * 1024 * 1024))
    receipt['files'].append(fetch(root, 'ollama/manifest.json', MANIFEST, 64 * 1024))
    manifest = json.loads((root / 'ollama/manifest.json').read_text(encoding='utf-8'))
    if args.pull_model:
        pull()
        receipt['files'].extend(model_files(root, manifest))
        with local('/api/show', {'model': MODEL}) as response:
            info = json.loads(response.read(1024 * 1024))
        receipt['model_capabilities'] = info.get('capabilities', [])
        architecture = info.get('model_info', {}).get('general.architecture', '')
        receipt['model_embedding_dimension'] = info.get('model_info', {}).get(architecture + '.embedding_length')
        receipt['model_embedding_capability_verified'] = 'embedding' in receipt['model_capabilities']
        receipt['model_runtime_verified'] = False
    path = root / 'component-receipt.json'
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Component receipt: ' + str(path), flush=True)


if __name__ == '__main__':
    main()
