"""Fetch only the explicitly approved, pinned offline CSL components.

Run explicitly by a maintainer; never called by the app or installer.
"""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PINS = {'citeproc': 'cc9153c45293af878de08cafddbefe6ea150c380',
        'styles': '89c63834393a5f806e375b0816dc110c3be93d44',
        'locales': 'a89adece41013402236e2c9020972d7e931fbab8'}
NODE = '24.14.1'
NODE_HASHES = {'node-v24.14.1-win-x64.zip': '6e50ce5498c0cebc20fd39ab3ff5df836ed2f8a31aa093cecad8497cff126d70',
               'node-v24.14.1.tar.xz': '7822507713f202cf2a551899d250259643f477b671706db421a6fb55c4aa0991'}


def fetch(spec):
    relative, url, expected = spec
    path = ROOT / relative
    if path.is_file():
        data = path.read_bytes()
        if expected and hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('Existing component hash mismatch: ' + relative)
    else:
        with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Kosh-component-build'}), timeout=120) as response:
            data = response.read(180 * 1024 * 1024 + 1)
        if len(data) > 180 * 1024 * 1024:
            raise ValueError('Component size limit exceeded.')
        if expected and hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('Official component checksum mismatch: ' + relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as output:
            output.write(data)
    return {'path': relative, 'url': url, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def main():
    raw = 'https://raw.githubusercontent.com/'
    specs = [('vendor/csl/citeproc.js', raw + 'Juris-M/citeproc-js/' + PINS['citeproc'] + '/citeproc_commonjs.js', None)]
    for name in ('LICENSE', 'AGPLv3'):
        specs.append(('vendor/csl/citeproc-' + name, raw + 'Juris-M/citeproc-js/' + PINS['citeproc'] + '/' + name, None))
    for name, upstream in (('vancouver.csl', 'nlm-citation-sequence.csl'), ('apa.csl', 'apa.csl'), ('ieee.csl', 'ieee.csl'), ('chicago-note.csl', 'chicago-notes-bibliography.csl')):
        specs.append(('vendor/csl/styles/' + name, raw + 'citation-style-language/styles/' + PINS['styles'] + '/' + upstream, None))
    specs.append(('vendor/csl/vancouver-nlm.csl', raw + 'citation-style-language/styles/' + PINS['styles'] + '/dependent/vancouver-nlm.csl', None))
    specs.append(('vendor/csl/styles-README.md', raw + 'citation-style-language/styles/' + PINS['styles'] + '/README.md', None))
    # The explicit maintainer operation restores the approved, pinned inventory
    # captured in the receipt, including all official locale XML files.
    inventory = json.loads((ROOT / 'vendor/csl/components.json').read_text(encoding='utf-8'))
    for name in inventory['locale_inventory']['files']:
        specs.append(('vendor/csl/locales/' + name, raw + 'citation-style-language/locales/' + PINS['locales'] + '/' + name, None))
    specs.append(('vendor/csl/locales-README.md', raw + 'citation-style-language/locales/' + PINS['locales'] + '/README.md', None))
    for name, digest in NODE_HASHES.items():
        specs.append(('work/csl-components/' + name, 'https://nodejs.org/dist/v' + NODE + '/' + name, digest))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        receipts = list(pool.map(fetch, specs))
    with zipfile.ZipFile(ROOT / 'work/csl-components' / ('node-v' + NODE + '-win-x64.zip')) as archive:
        for name in ('node.exe', 'LICENSE'):
            data = archive.read('node-v' + NODE + '-win-x64/' + name)
            target = ROOT / 'tools/node' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and target.read_bytes() != data:
                raise ValueError('Existing Node component differs: ' + name)
            if not target.exists():
                target.write_bytes(data)
            receipts.append({'path': target.relative_to(ROOT).as_posix(), 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'archive': 'node-v' + NODE + '-win-x64.zip'})
    receipt = {'pins': PINS, 'node': NODE, 'files': receipts, 'locale_inventory': inventory['locale_inventory'], 'approval': 'PG explicitly approved these component sources and file classes in the Kosh signing/citation/math fix request.'}
    (ROOT / 'vendor/csl/components.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'files': len(receipts), 'node': NODE, 'pins': PINS}))


if __name__ == '__main__':
    main()
