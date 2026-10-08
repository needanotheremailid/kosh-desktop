"""Cheap explicit component availability, with positively allowlisted diagnostics.

No Store/data input, recursive scans, subprocesses, hashes, model contact or raw
diagnostics. Availability does not prove integrity or successful document work.
"""
import importlib
from pathlib import Path
import platform
import re
import sys


DEVELOPMENT_NODE = Path(r'C:\Program Files\nodejs\node.exe')
INSTALLED_TESSDATA = Path(r'C:\Program Files\Tesseract-OCR\tessdata')
COMPONENTS = {'python': 'required', 'pdf': 'required', 'docx': 'required', 'csl': 'required',
              'tex': 'optional', 'ocr': 'optional', 'local_model': 'optional'}
LANGUAGES = ('eng', 'hin', 'pan')
STATUSES = {'available', 'missing', 'error', 'not_checked'}
ORIGINS = {'bundled', 'development', 'external', 'current_runtime', 'installed', 'none', 'unknown'}
CODES = {'AVAILABLE', 'COMPONENT_MISSING', 'CHECK_FAILED', 'DEVELOPMENT_RUNTIME', 'EXTERNAL_RUNTIME',
         'DEPENDENCY_UNAVAILABLE', 'OCR_LANGUAGE_MISSING', 'OCR_API_UNAVAILABLE', 'NO_MODEL_CONTACT'}
CSL_FILES = ('scripts/csl_render.js', 'vendor/csl/citeproc.js', 'vendor/csl/locales/locales-en-US.xml',
             'vendor/csl/styles/vancouver.csl', 'vendor/csl/styles/apa.csl',
             'vendor/csl/styles/ieee.csl', 'vendor/csl/styles/chicago-note.csl')
VERSION_PATTERN = r'(?:0|[1-9]\d{0,2})\.(?:0|[1-9]\d{0,2})\.(?:0|[1-9]\d{0,2})(?:-rc\.[1-9]\d{0,5})?'


def _row(status, code, origin='none'):
    return {'status': status, 'origin': origin, 'code': code}


def _file(path):
    try:
        return 'available' if path.is_file() and path.stat().st_size > 0 else 'missing'
    except OSError:
        return 'error'


def _files(paths, origin='bundled'):
    states = [_file(path) for path in paths]
    if 'error' in states:
        return _row('error', 'CHECK_FAILED')
    if 'missing' in states:
        return _row('missing', 'COMPONENT_MISSING')
    return _row('available', 'AVAILABLE', origin)


def _module(name, attribute):
    try:
        module = importlib.import_module(name)
        if not callable(getattr(module, attribute, None)):
            return _row('missing', 'COMPONENT_MISSING'), None
        return _row('available', 'AVAILABLE', 'current_runtime'), module
    except ImportError:
        return _row('missing', 'COMPONENT_MISSING'), None
    except Exception:
        return _row('error', 'CHECK_FAILED'), None


def _safe_text(value, pattern):
    return value if isinstance(value, str) and re.fullmatch(pattern, value) else 'unknown'


def _safe_row(value, requirement):
    if not isinstance(value, dict):
        value = _row('error', 'CHECK_FAILED')
    status = value.get('status')
    code = value.get('code')
    origin = value.get('origin')
    # New output is constructed solely from fixed enums, never copied error text.
    if not isinstance(status, str) or status not in STATUSES or not isinstance(code, str) or code not in CODES:
        return {'requirement': requirement, **_row('error', 'CHECK_FAILED')}
    return {'requirement': requirement, 'status': status,
            'origin': origin if isinstance(origin, str) and origin in ORIGINS else 'unknown', 'code': code}


def diagnostics(report):
    """Build the complete export allowlist; never serialize input or private extras."""
    report = report if isinstance(report, dict) else {}
    app = report.get('app') if isinstance(report.get('app'), dict) else {}
    operating = report.get('os') if isinstance(report.get('os'), dict) else {}
    components = report.get('components') if isinstance(report.get('components'), dict) else {}
    languages = report.get('languages') if isinstance(report.get('languages'), dict) else {}
    return {'schema_version': 1,
            'app': {'version': _safe_text(app.get('version'), VERSION_PATTERN),
                    'build': _safe_text(app.get('build'), r'[a-f0-9]{64}')},
            'os': {'family': operating.get('family') if operating.get('family') in ('Windows', 'Linux', 'macOS', 'Other') else 'Other',
                   'version': _safe_text(operating.get('version'), r'\d{1,6}(?:\.\d{1,6}){0,3}')},
            'components': {name: _safe_row(components.get(name), requirement) for name, requirement in COMPONENTS.items()},
            'languages': {language: _safe_row(languages.get(language), 'optional') for language in LANGUAGES}}


def check(root, *, app_version, app_build):
    """Probe only fixed package files and local imports on an explicit UI request."""
    root = Path(root)
    components = {}
    binary = root / 'runtime/python.exe'
    bundled = _file(binary)
    installation_marker = _file(root / 'INSTALL_RECEIPT.json')
    if bundled == 'error':
        components['python'] = _row('error', 'CHECK_FAILED')
    elif bundled == 'available':
        try:
            current = Path(sys.executable).resolve() == binary.resolve()
            components['python'] = _row('available', 'AVAILABLE' if current else 'EXTERNAL_RUNTIME', 'bundled' if current else 'external')
        except OSError:
            components['python'] = _row('error', 'CHECK_FAILED')
    elif installation_marker == 'error':
        components['python'] = _row('error', 'CHECK_FAILED')
    elif installation_marker == 'available':
        components['python'] = _row('missing', 'COMPONENT_MISSING')
    else:
        components['python'] = _row('available', 'DEVELOPMENT_RUNTIME', 'development')
    components['pdf'], pdf = _module('pymupdf', 'open')
    components['docx'], _ = _module('docx', 'Document')
    node = _files([root / 'tools/node/node.exe'])
    if node['status'] == 'missing' and _file(DEVELOPMENT_NODE) == 'available':
        node = _row('available', 'EXTERNAL_RUNTIME', 'external')
    resources = _files([root / name for name in CSL_FILES])
    components['csl'] = resources if resources['status'] != 'available' else node
    components['tex'] = _files([root / 'tools/tectonic/tectonic.exe', root / 'vendor/tex/kosh-tex.zip'])
    languages = {}
    for language in LANGUAGES:
        bundled_language = _files([root / 'tessdata' / (language + '.traineddata')])
        external = _file(INSTALLED_TESSDATA / (language + '.traineddata')) if bundled_language['status'] == 'missing' else 'missing'
        languages[language] = (_row('available', 'AVAILABLE', 'installed') if external == 'available'
                               else _row('error', 'CHECK_FAILED') if external == 'error' else bundled_language)
    if pdf is None:
        components['ocr'] = _row('missing', 'DEPENDENCY_UNAVAILABLE')
    elif not callable(getattr(getattr(pdf, 'Page', None), 'get_textpage_ocr', None)):
        components['ocr'] = _row('missing', 'OCR_API_UNAVAILABLE')
    elif not any(value['status'] == 'available' for value in languages.values()):
        components['ocr'] = _row('missing', 'OCR_LANGUAGE_MISSING')
    else:
        components['ocr'] = _row('available', 'AVAILABLE', 'current_runtime')
    components['local_model'] = _row('not_checked', 'NO_MODEL_CONTACT')
    try:
        family = {'Windows': 'Windows', 'Linux': 'Linux', 'Darwin': 'macOS'}.get(platform.system(), 'Other')
        os_version = platform.version() if family == 'Windows' else platform.mac_ver()[0] if family == 'macOS' else platform.release()
    except Exception:
        family, os_version = 'Other', 'unknown'
    return diagnostics({'app': {'version': app_version, 'build': app_build},
                        'os': {'family': family, 'version': os_version}, 'components': components, 'languages': languages})
