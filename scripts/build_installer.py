"""Bundle this source release with the installed runtime. No network or installers."""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_MODULES = ('pymupdf', 'fitz', 'docx', 'lxml', 'typing_extensions.py')
PACKAGE_NAMES = ('PyMuPDF', 'python-docx', 'lxml', 'typing_extensions')
SOURCE_FILES = {'runtime-files.json', 'backend.py', 'server.py', 'agent.py', 'literature.py', 'folder_edits.py', 'assistance.py', 'bibliography.py', 'manuscript.py', 'citations.py', 'completion.py', 'exports.py', 'retrieval.py', 'folder_assist.py', 'mcp_server.py', 'upgrade.py', 'build.ps1', 'check-runtime.ps1',
                'setup.ps1', 'install-shortcuts.ps1', 'export-source.ps1', 'build-installer.ps1',
                'Open Research.cmd', 'Setup Research.cmd', 'requirements.txt', 'README.md',
                'USER_GUIDE.md', 'FEATURES.md', 'CONTRIBUTING.md', 'SECURITY.md', 'AGENT_API.md',
                '.gitignore', 'LICENSE', 'THIRD_PARTY.md', 'CREDITS.md', 'SIGNING.md', 'csl_engine.py', 'csl_styles.py', 'pdf_math.py', 'scripts/sign-release.ps1', 'word_citations.py','citation_notes.py','manuscript_templates.py','tex_compile.py','vendor/tex/receipt.json','vendor/tex/LICENSE.tectonic'}
LEGAL_TEMPLATES = {'pymupdf': 'pymupdf-{}.tar.gz', 'python-docx': 'python_docx-{}.tar.gz',
                   'lxml': 'lxml-{}.tar.gz', 'typing-extensions': 'typing_extensions-{}.tar.gz',
                   'python': 'Python-{}.tar.xz', 'mupdf': 'mupdf-{}-source.tar.gz'}
SOURCE_FILES.add('BUILDING.md')


def normalized_name(name):
    return name.lower().replace('_', '-')


def safe_relative(name):
    path = PurePosixPath(name)
    if '\\' in name or not name or path.is_absolute() or any(part in ('', '.', '..') or ':' in part for part in path.parts):
        raise ValueError('Unsafe archive path.')
    if path.as_posix() != name:
        raise ValueError('Archive path is not canonical.')
    return path


def source_allowed(name):
    path = safe_relative(name)
    return name in SOURCE_FILES or (path.parts[:2] == ('vendor', 'csl') and path.suffix.lower() in {'.js', '.json', '.csl', '.xml', '.md', ''}) or (
        len(path.parts) >= 2 and path.parts[0] in {'native', 'ui', 'tests', 'assets', 'scripts'}
        and path.suffix.lower() in {'.cs', '.html', '.css', '.js', '.py', '.ico', '.png', '.svg'}
        and '__pycache__' not in path.parts)


def read_source(source_zip):
    with zipfile.ZipFile(source_zip) as archive:
        names = archive.namelist()
        if len(names) > 5000 or len(set(n.casefold() for n in names)) != len(names):
            raise ValueError('Source release has excessive or duplicated entries.')
        manifest = json.loads(archive.read('release-manifest.json'))
        if manifest.get('kind') != 'source-release' or manifest.get('includes_user_data') is not False:
            raise ValueError('Expected a verified source-only release.')
        expected = {row['path']: row for row in manifest['files']}
        if set(names) != set(expected) | {'release-manifest.json'}:
            raise ValueError('Source release manifest does not match its entries.')
        result = {}
        for name, row in expected.items():
            if not source_allowed(name):
                raise ValueError('Unexpected source release file: ' + name)
            entry = archive.getinfo(name)
            if entry.file_size > 32 * 1024 * 1024:
                raise ValueError('Source file exceeds package limit.')
            data = archive.read(name)
            if len(data) != row['size'] or hashlib.sha256(data).hexdigest() != row['sha256']:
                raise ValueError('Source release hash mismatch: ' + name)
            result[name] = data
        for name in ('backend.py', 'server.py', 'agent.py', 'literature.py', 'folder_edits.py', 'native/Launcher.cs', 'ui/index.html', 'ui/app.js', 'ui/app.css', 'assets/App.ico', 'LICENSE', 'THIRD_PARTY.md', 'CREDITS.md'):
            if name not in result:
                raise ValueError('Source release is missing required application files.')
        return result


def identity(files):
    digest = hashlib.sha256()
    names = json.loads(files['runtime-files.json'])
    for name in sorted(names):
        safe_relative(name)
        digest.update(name.encode('utf-8'))
        digest.update(files[name])
    return digest.hexdigest()


def add_tree(files, source, destination, excluded=()):
    for path in sorted(source.rglob('*')):
        relative = path.relative_to(source)
        if path.is_symlink():
            raise ValueError('Runtime contains a symbolic link; inspect it before packaging.')
        if not path.is_file() or any(part in set(excluded) | {'__pycache__'} for part in relative.parts) or path.suffix == '.pyc':
            continue
        if path.name in {'direct_url.json', 'sitecustomize.py', 'usercustomize.py'}:
            continue
        files[(PurePosixPath(destination) / PurePosixPath(relative.as_posix())).as_posix()] = path.read_bytes()


def runtime_payload(files):
    runtime = Path(sys.base_prefix).resolve()
    if sys.version_info[:2] != (3, 12) or not (runtime / 'python.exe').is_file():
        raise ValueError('This package requires the installed Windows Python 3.12 runtime.')
    for path in runtime.iterdir():
        if path.is_file() and (path.name in {'python.exe', 'pythonw.exe', 'LICENSE.txt'} or path.suffix.lower() == '.dll'):
            files['runtime/' + path.name] = path.read_bytes()
    add_tree(files, runtime / 'DLLs', 'runtime/DLLs', excluded=('_tkinter.pyd', 'tcl86t.dll', 'tk86t.dll'))
    add_tree(files, runtime / 'Lib', 'runtime/Lib', excluded=('site-packages', 'test', 'tests', 'idlelib', 'tkinter', 'turtledemo', 'venv', 'ensurepip'))
    packages = runtime / 'Lib' / 'site-packages'
    # Query only the directory whose bytes will be bundled, never a user-site
    # distribution that happens to precede it on sys.path.
    distributions = {}
    for distribution in importlib.metadata.distributions(path=[str(packages)]):
        name = normalized_name(distribution.metadata.get('Name', ''))
        if name in {normalized_name(item) for item in PACKAGE_NAMES}:
            if name in distributions:
                raise ValueError('Ambiguous installed distribution in copied runtime: ' + name)
            directory = Path(distribution._path).resolve()
            if directory.parent != packages.resolve():
                raise ValueError('Distribution metadata escaped the copied runtime.')
            distributions[name] = distribution
    for name in PACKAGE_MODULES:
        source = packages / name
        if source.is_symlink() or not source.resolve().is_relative_to(packages.resolve()):
            raise ValueError('Installed package source escaped the copied runtime.')
        module_name = name[:-3] if name.endswith('.py') else name
        # fitz is the deprecated compatibility alias; inspect its resolution
        # without executing its import-time warning. The app uses pymupdf.
        module_file = Path(importlib.util.find_spec(module_name).origin).resolve() if name == 'fitz' else Path(importlib.import_module(module_name).__file__).resolve()
        if not (module_file == source.resolve() if source.is_file() else module_file.is_relative_to(source.resolve())):
            raise ValueError('Loaded package origin does not match the directory being copied: ' + name)
        if source.is_dir():
            add_tree(files, source, 'runtime/Lib/site-packages/' + name, excluded=('tests',))
        elif source.is_file():
            files['runtime/Lib/site-packages/' + name] = source.read_bytes()
        else:
            raise ValueError('Required installed package is missing: ' + name)
    provenance = []
    versions = {'python': sys.version.split()[0]}
    for name in PACKAGE_NAMES:
        key = normalized_name(name)
        if key not in distributions:
            raise ValueError('Distribution metadata is absent from copied runtime: ' + name)
        distribution = distributions[key]
        directory = Path(distribution._path)
        add_tree(files, directory, 'runtime/Lib/site-packages/' + directory.name)
        versions[key] = distribution.version
        provenance.append({'package': name, 'version': distribution.version,
                           'license': distribution.metadata.get('License-Expression') or distribution.metadata.get('License'),
                           'project_urls': distribution.metadata.get_all('Project-URL') or [],
                           'license_files': [str(file) for file in distribution.files or [] if 'license' in str(file).lower() or 'copying' in str(file).lower()]})
    versions['mupdf'] = importlib.import_module('pymupdf').VersionFitz
    files['RUNTIME_COMPONENTS.json'] = json.dumps({'python': sys.version.split()[0], 'mupdf': versions['mupdf'], 'packages': provenance,
        'notice': 'Installed components were copied with their available license files. This inventory is not a redistribution compliance determination. PyMuPDF declares AGPL-3.0 or an Artifex commercial license. Review the bundled notices and corresponding source before sharing.'}, indent=2).encode()
    return versions


def legal_payload(files, directory, versions):
    """Accept a complete prepared source bundle only after receipt verification."""
    directory = directory.resolve()
    receipt_path = directory / 'source-receipts.json'
    copying_path = directory / 'PyMuPDF-COPYING.txt'
    if not directory.is_dir() or not receipt_path.is_file() or not copying_path.is_file():
        raise ValueError('Prepared legal bundle needs source-receipts.json and full PyMuPDF COPYING.')
    copying = copying_path.read_bytes()
    if len(copying) < 30000 or b'GNU AFFERO GENERAL PUBLIC LICENSE' not in copying:
        raise ValueError('Full PyMuPDF AGPL COPYING text is required, not its one-line notice.')
    receipts = json.loads(receipt_path.read_text(encoding='utf-8-sig'))
    if not isinstance(receipts, list) or len(receipts) != len(LEGAL_TEMPLATES):
        raise ValueError('Legal source receipts must cover all six runtime components.')
    prepared = {'legal/source-receipts.json': receipt_path.read_bytes(), 'legal/PyMuPDF-COPYING.txt': copying}
    seen = set()
    for row in receipts:
        if not isinstance(row, dict) or not isinstance(row.get('package'), str):
            raise ValueError('Malformed legal source receipt.')
        package = normalized_name(row['package'])
        if package not in LEGAL_TEMPLATES or package in seen or row.get('version') != versions.get(package):
            raise ValueError('Legal source version differs from the copied runtime: ' + package)
        name = LEGAL_TEMPLATES[package].format(versions[package])
        if row.get('file') != name:
            raise ValueError('Legal source archive name does not match its component version.')
        safe_relative(name)
        path = directory / name
        if path.is_symlink() or not path.is_file() or path.resolve().parent != directory:
            raise ValueError('A required legal source archive is missing or outside the bundle.')
        data = path.read_bytes()
        if len(data) != row.get('bytes') or hashlib.sha256(data).hexdigest() != row.get('sha256'):
            raise ValueError('Legal source receipt size/hash mismatch: ' + name)
        prepared['legal/' + name] = data
        seen.add(package)
    files.update(prepared)


def verify_payload_requirements(files, versions):
    required = {'LICENSE', 'THIRD_PARTY.md', 'CREDITS.md', 'RUNTIME_COMPONENTS.json',
                'runtime/LICENSE.txt', 'legal/source-receipts.json', 'legal/PyMuPDF-COPYING.txt'}
    required.update('legal/' + template.format(versions[name]) for name, template in LEGAL_TEMPLATES.items())
    if required - set(files):
        raise ValueError('Package is missing required application/runtime licence or corresponding-source material.')
    if any(len(data) > 256 * 1024 * 1024 for data in files.values()) or sum(map(len, files.values())) > 1024 * 1024 * 1024:
        raise ValueError('Package exceeds installer file/total size bounds.')


def ocr_payload(files, directory):
    """Bundle only the approved OCR bytes after receipt/hash verification."""
    directory = directory.resolve()
    receipt = json.loads((directory / 'component-receipt.json').read_text(encoding='utf-8-sig'))
    expected = {'tessdata/eng.traineddata', 'tessdata/hin.traineddata', 'tessdata/pan.traineddata',
                'licences/tessdata_fast_LICENSE.txt', 'licences/tessdata_best_LICENSE.txt'}
    rows = [row for row in receipt['files'] if row['path'] in expected]
    if {row['path'] for row in rows} != expected or len(rows) != len(expected):
        raise ValueError('OCR receipt must include exactly the approved languages and licence files.')
    for row in rows:
        path = directory / row['path']
        if path.is_symlink() or not path.resolve().is_relative_to(directory):
            raise ValueError('OCR component escaped its prepared folder.')
        data = path.read_bytes()
        if len(data) != row['bytes'] or hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError('OCR receipt hash mismatch: ' + row['path'])
        files[row['path']] = data
    files['legal/ocr-receipts.json'] = json.dumps({'files': rows, 'verified_at': receipt['verified_at']}, indent=2).encode()


def csl_payload(files):
    if 'vendor/csl/components.json' not in files:
        raise ValueError('CSL source receipt is missing from the source release.')
    receipt = json.loads(files['vendor/csl/components.json'])
    required = {'vendor/csl/citeproc.js', 'vendor/csl/citeproc-LICENSE', 'vendor/csl/citeproc-AGPLv3',
                'vendor/csl/styles/apa.csl', 'vendor/csl/styles/ieee.csl', 'vendor/csl/styles/vancouver.csl',
                'vendor/csl/locales/locales-en-US.xml', 'vendor/csl/styles-README.md', 'vendor/csl/locales-README.md',
                'tools/node/node.exe', 'tools/node/LICENSE', 'work/csl-components/node-v24.14.1.tar.xz'}
    seen = set()
    for row in receipt['files']:
        if row['path'].startswith('vendor/csl/'):
            required.add(row['path'])
    for row in receipt['files']:
        name = row['path']
        if name not in required:
            continue
        safe_relative(name)
        if name.startswith('vendor/'):
            data = files.get(name)
        else:
            path = ROOT / name
            if path.is_symlink() or not path.is_file():
                raise ValueError('Approved offline CSL component is missing: ' + name)
            data = path.read_bytes()
        if data is None or len(data) != row['size'] or hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError('CSL source/runtime receipt mismatch: ' + name)
        files['legal/node-v24.14.1.tar.xz' if name.startswith('work/') else name] = data
        seen.add(name)
    if seen != required:
        raise ValueError('CSL component receipt omits a required runtime/source/licence.')


def tex_payload(files):
    receipt_name = 'vendor/tex/receipt.json'
    if receipt_name not in files:
        raise ValueError('Offline TeX receipt is missing from the source release.')
    receipt = json.loads(files[receipt_name])
    required = {'tools/tectonic/tectonic.exe', 'vendor/tex/kosh-tex.zip', 'vendor/tex/LICENSE.tectonic'}
    legal_names = {'source-version-audit.json', 'texlive-source-receipt.json',
                   'tectonic-0.17.0-source.tar.gz', 'tectonic-0.17.0-windows-msvc.zip',
                   'setspace.doc.r24881.tar.xz', 'unicode-data.doc.r60516.tar.xz'}
    legal_names.update({'amsfonts.doc.r61937.tar.xz', 'amsfonts.source.r61937.tar.xz',
                       'amsfonts.r61937.tar.xz', 'cm.doc.r57963.tar.xz', 'cm.r57963.tar.xz',
                       'lm.doc.r61719.tar.xz', 'lm.r61719.tar.xz'})
    for package, revision in [('amsmath',61041), ('fancyhdr',57672), ('fontspec',61617),
                              ('geometry',61719), ('graphics',61315), ('hyperref',62142),
                              ('hyph-utf8',61719), ('latex',61232), ('lineno',61719), ('tex-gyre',48058)]:
        for kind in ('doc', 'source'):
            legal_names.add(f'{package}.{kind}.r{revision}.tar.xz')
    required.update('work/tex-components/' + name for name in legal_names)
    seen = set()
    for row in receipt['payload_files']:
        name = row['path']
        relative = safe_relative(name)
        if name in seen or not (name.startswith('vendor/tex/') or name == 'tools/tectonic/tectonic.exe' or name.startswith('work/tex-components/')):
            raise ValueError('Unexpected or duplicate TeX payload path.')
        path = ROOT / relative
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()) or not path.is_file():
            raise ValueError('Approved TeX component is missing or escaped the repository.')
        data = files.get(name, path.read_bytes())
        if len(data) != row['bytes'] or hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError('TeX component receipt mismatch: ' + name)
        destination = 'legal/tex/' + relative.name if name.startswith('work/') else name
        if destination in files and files[destination] != data:
            raise ValueError('TeX component destination collision.')
        files[destination] = data
        seen.add(name)
    if seen != required:
        raise ValueError('TeX receipt differs from the required runtime, matching source and licence inventory.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-zip', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--legal-dir', type=Path, required=True, help='Complete verified dependency-license/source bundle; copied under legal/')
    parser.add_argument('--components-dir', type=Path, required=True, help='Prepared approved OCR components and hash receipts')
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() or not output.parent.is_dir():
        raise ValueError('Choose a new installer filename in an existing output folder.')
    if not sys.flags.ignore_environment or not sys.flags.no_user_site:
        raise ValueError('Run through build-installer.ps1 or python -E -s so user/environment modules cannot shadow the copied runtime.')
    files = read_source(args.source_zip)
    build = identity(files)
    versions = runtime_payload(files)
    legal_payload(files, args.legal_dir, versions)
    ocr_payload(files, args.components_dir)
    csl_payload(files)
    tex_payload(files)
    verify_payload_requirements(files, versions)
    installer = ROOT / 'native' / 'Installer.cs'
    if not installer.is_file() or not args.compiler.is_file():
        raise ValueError('Installed .NET compiler or installer source is missing.')
    (ROOT / 'work').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='kosh-build-', dir=ROOT / 'work') as temporary:
        stage = Path(temporary)
        launcher_source = stage / 'Launcher.cs'
        launcher_source.write_bytes(files['native/Launcher.cs'])
        icon = stage / 'App.ico'
        icon.write_bytes(files['assets/App.ico'])
        launcher = stage / 'ResearchDesktop.exe'
        common = [str(args.compiler), '/nologo', '/target:winexe', '/optimize+', '/reference:System.Windows.Forms.dll', '/reference:System.Web.Extensions.dll', '/win32icon:' + str(icon)]
        subprocess.run([*common, '/out:' + str(launcher), str(launcher_source)], check=True)
        files['bin/ResearchDesktop.exe'] = launcher.read_bytes()
        manifest = {'format': 1, 'app': 'pg-research-desktop', 'build': build,
                    'files': [{'path': name, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()} for name, data in sorted(files.items())]}
        payload = stage / 'payload.zip'
        with zipfile.ZipFile(payload, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for name, data in sorted(files.items()):
                archive.writestr(name, data)
            archive.writestr('package-manifest.json', json.dumps(manifest, separators=(',', ':')).encode())
        built = stage / 'KoshSetup.exe'
        installer_source = stage / 'Installer.cs'
        installer_source.write_bytes(files.get('native/Installer.cs', installer.read_bytes()))
        subprocess.run([*common, '/reference:System.IO.Compression.dll', '/reference:System.IO.Compression.FileSystem.dll', '/resource:' + str(payload) + ',Kosh.Payload.zip', '/out:' + str(built), str(installer_source)], check=True)
        with output.open('xb') as destination, built.open('rb') as source:
            shutil.copyfileobj(source, destination)
        print(json.dumps({'installer': str(output), 'bytes': output.stat().st_size, 'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
                          'build': build, 'payload_files': len(files), 'payload_bytes': sum(len(data) for data in files.values()),
                          'source_zip': str(args.source_zip.resolve()), 'distribution_status': 'local-build-only; packaged notices/source review required before sharing'}))


if __name__ == '__main__':
    main()
