"""Maintainer-only: pin an approved isolated Tectonic cache into an offline ZIP.

No network operation occurs here. Populate the cache from the approved official
bundle with a synthetic feature fixture, then supply its directory and archive
paths. Source/license inputs must be reviewed separately before distribution.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile
import shutil
import tarfile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def latin_modern_resources(resources, legal_input=None):
    """Close default TU font families from the already reviewed local archive."""
    definitions = ('tulmr.fd', 'tulmss.fd', 'tulmtt.fd')
    referenced = set()
    for name in definitions:
        if name not in resources:
            raise ValueError('Latin Modern font definition is missing: ' + name)
        names = re.findall(r'\\UnicodeFontFile\{([^}]+)\}', resources[name].decode('utf-8'))
        if not names or any(not re.fullmatch(r'lm[a-z0-9-]+', value) for value in names):
            raise ValueError('Unexpected Latin Modern font definition.')
        referenced.update(value + '.otf' for value in names)
    missing = referenced - resources.keys()
    if not legal_input:
        if missing:
            raise ValueError('Default Latin Modern fonts are incomplete; supply reviewed lm.r61719.tar.xz source inputs.')
        return {}, {'definitions': list(definitions), 'referenced_fonts': len(referenced), 'added_fonts': []}
    source_name = 'lm.r61719.tar.xz'
    source = legal_input / source_name
    receipt = json.loads((legal_input / 'receipt.json').read_text())
    rows = [row for row in receipt['files'] if row['file'] == source_name]
    if len(rows) != 1 or digest(source) != rows[0]['sha256']:
        raise ValueError('Reviewed Latin Modern source archive receipt mismatch.')
    additions, matches = {}, []
    with tarfile.open(source, 'r:xz') as archive:
        members = {member.name: member for member in archive.getmembers() if member.isfile()}
        for name in sorted(referenced):
            origin = 'fonts/opentype/public/lm/' + name
            member = members.get(origin)
            if member is None or not 0 < member.size <= 2_000_000:
                raise ValueError('Reviewed Latin Modern archive omits font: ' + name)
            data = archive.extractfile(member).read()
            if name in resources and resources[name] != data:
                raise ValueError('Cached Latin Modern font differs from reviewed source: ' + name)
            if name in missing:
                additions[name] = data
            matches.append({'runtime_file': name, 'source_archive': source_name, 'original_member': origin,
                            'sha256': hashlib.sha256(data).hexdigest()})
    return additions, {'definitions': list(definitions), 'referenced_fonts': len(referenced),
                       'added_fonts': sorted(additions), 'source_archive': source_name,
                       'source_archive_sha256': digest(source), 'matched_files': matches}


def pack(cache, output, binary_archive, source_archive, legal_input=None):
    output = output.resolve()
    roots = list((cache / 'bundles' / 'data').glob('*.index'))
    if len(roots) != 1:
        raise ValueError('Expected exactly one approved bundle cache.')
    bundle_id = roots[0].stem
    resources = roots[0].with_suffix('')
    files = {path.name: path.read_bytes() for path in resources.iterdir() if path.is_file()}
    additions, latin_modern = latin_modern_resources(files, legal_input)
    files.update(additions)
    if not files or sum(len(content) for content in files.values()) > 100_000_000:
        raise ValueError('Empty or oversized resource subset.')
    output.mkdir(parents=True, exist_ok=True)
    archive = output / 'kosh-tex.zip'
    entries = []
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as package:
        # ZipBundle requires the upstream bundle identity entry.
        def write_entry(name, content):
            entry = zipfile.ZipInfo(name, date_time=(2000, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            package.writestr(entry, content)
        write_entry('SHA256SUM', (bundle_id + '\n').encode())
        for name, content in sorted(files.items(), key=lambda item: item[0].casefold()):
            write_entry(name, content)
            entries.append({'name': name, 'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()})
    receipt = {'compiler_version': '0.17.0',
               'binary_url': 'https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.17.0/tectonic-0.17.0-x86_64-pc-windows-msvc.zip',
               'binary_archive_sha256': digest(binary_archive),
               'source_url': 'https://api.github.com/repos/tectonic-typesetting/tectonic/tarball/tectonic%400.17.0',
               'source_archive_sha256': digest(source_archive),
               'bundle_url': 'https://relay.fullyjustified.net/default_bundle_v33.tar',
               'upstream_bundle_identity': bundle_id,
               'bundle_index_sha256': digest(roots[0]),
               'archive_sha256': digest(archive), 'files': entries, 'latin_modern': latin_modern,
               'scope': 'Selected official resource bytes, unchanged; no runtime network or system TeX installation.',
               'license_boundary': 'Per-file embedded notices retained. Matching external package source/license coverage must be supplied before distribution.'}
    root = Path(__file__).resolve().parent.parent
    legal_output = root / 'work' / 'tex-components'
    legal_output.mkdir(parents=True, exist_ok=True)
    legal_paths = []
    for origin, name in ((binary_archive, 'tectonic-0.17.0-windows-msvc.zip'),
                         (source_archive, 'tectonic-0.17.0-source.tar.gz')):
        shutil.copyfile(origin, legal_output / name)
        legal_paths.append(legal_output / name)
    if legal_input:
        legal_receipt = json.loads((legal_input / 'receipt.json').read_text())
        for item in legal_receipt['files']:
            if Path(item['file']).name != item['file'] or '\\' in item['file']:
                raise ValueError('Source receipt must contain simple filenames.')
            origin = legal_input / item['file']
            if digest(origin) != item['sha256']:
                raise ValueError('Source receipt mismatch.')
            shutil.copyfile(origin, legal_output / item['file'])
            legal_paths.append(legal_output / item['file'])
        shutil.copyfile(legal_input / 'receipt.json', legal_output / 'texlive-source-receipt.json')
        legal_paths.append(legal_output / 'texlive-source-receipt.json')
        receipt['texlive_source_receipt'] = 'work/tex-components/texlive-source-receipt.json'
        receipt['license_boundary'] = 'Unchanged embedded notices and selected matching historical source/documentation archives supplied; see source-version-audit.json.'
    with tarfile.open(source_archive) as upstream:
        license_member = next(item for item in upstream.getmembers()
                              if item.name.endswith('/LICENSE') and item.name.count('/') == 1)
        (output / 'LICENSE.tectonic').write_bytes(upstream.extractfile(license_member).read())
    payload = [root / 'tools' / 'tectonic' / 'tectonic.exe', archive,
               output / 'LICENSE.tectonic'] + sorted(legal_paths)
    audit = legal_output / 'source-version-audit.json'
    if audit.is_file():
        payload.append(audit)
    receipt['payload_files'] = [{'path': path.relative_to(root).as_posix(), 'bytes': path.stat().st_size,
                                 'sha256': digest(path)} for path in payload]
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for argument in ('cache', 'output', 'binary_archive', 'source_archive'):
        parser.add_argument('--' + argument.replace('_', '-'), type=Path, required=True)
    parser.add_argument('--legal-input', type=Path)
    args = parser.parse_args()
    result = pack(args.cache, args.output, args.binary_archive, args.source_archive, args.legal_input)
    print(json.dumps({'files': len(result['files']), 'sha256': result['archive_sha256']}))
