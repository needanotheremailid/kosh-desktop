"""Availability and diagnostic privacy checks use fixed invented component fixtures."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from installation_health import check, diagnostics, COMPONENTS
import installation_health as health
from updater import CURRENT_VERSION


class InstallationHealth(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.build = 'a' * 64
        self.pdf = SimpleNamespace(open=lambda: None, Page=SimpleNamespace(get_textpage_ocr=lambda: None))
        self.docx = SimpleNamespace(Document=lambda: None)

    def file(self, name):
        target = self.root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'Invented component placeholder; not executed.')
        return target

    def report(self, **kwargs):
        modules = {'pymupdf': self.pdf, 'docx': self.docx}
        with patch.object(health, 'DEVELOPMENT_NODE', self.root / 'outside-node.exe'), \
                patch.object(health, 'INSTALLED_TESSDATA', self.root / 'outside-tessdata'), \
                patch.object(health.importlib, 'import_module', side_effect=lambda name: modules[name]):
            return check(self.root, app_version='1.0.0', app_build=self.build, **kwargs)

    def complete_files(self):
        for name in ('runtime/python.exe', 'INSTALL_RECEIPT.json', 'tools/node/node.exe',
                     'scripts/csl_render.js', 'vendor/csl/citeproc.js', 'vendor/csl/styles/vancouver.csl',
                     'vendor/csl/styles/apa.csl', 'vendor/csl/styles/ieee.csl', 'vendor/csl/styles/chicago-note.csl',
                     'vendor/csl/locales/locales-en-US.xml', 'tools/tectonic/tectonic.exe', 'vendor/tex/kosh-tex.zip',
                     'tessdata/eng.traineddata', 'tessdata/hin.traineddata', 'tessdata/pan.traineddata'):
            self.file(name)

    def test_complete_availability_and_required_optional_are_explicit(self):
        self.complete_files()
        with patch('installation_health.sys.executable', str(self.root / 'runtime/python.exe')):
            report = self.report()
        self.assertEqual(report['app'], {'version': '1.0.0', 'build': self.build})
        self.assertEqual(set(report['components']), {'python', 'pdf', 'docx', 'csl', 'tex', 'ocr', 'local_model'})
        for name in ('python', 'pdf', 'docx', 'csl'):
            self.assertEqual(report['components'][name]['status'], 'available')
            self.assertEqual(report['components'][name]['requirement'], 'required')
        for name in ('tex', 'ocr', 'local_model'):
            self.assertEqual(report['components'][name]['requirement'], 'optional')
        self.assertEqual(report['components']['local_model']['status'], 'not_checked')
        self.assertEqual(report['components']['local_model']['code'], 'NO_MODEL_CONTACT')
        self.assertEqual([report['languages'][language]['status'] for language in ('eng', 'hin', 'pan')], ['available'] * 3)

    def test_missing_files_import_failure_and_empty_files_have_fixed_codes(self):
        self.file('INSTALL_RECEIPT.json')
        report = self.report()
        self.assertEqual(report['components']['python']['status'], 'missing')
        self.assertEqual(report['components']['csl']['code'], 'COMPONENT_MISSING')
        self.assertEqual(report['components']['tex']['status'], 'missing')
        self.assertEqual(report['components']['ocr']['code'], 'OCR_LANGUAGE_MISSING')
        self.file('tools/tectonic/tectonic.exe').write_bytes(b'')
        self.file('vendor/tex/kosh-tex.zip')
        self.assertEqual(self.report()['components']['tex']['status'], 'missing')
        with patch('installation_health.importlib.import_module', side_effect=ImportError('private user source secret')):
            report = check(self.root, app_version='1.0.0', app_build=self.build)
        self.assertEqual(report['components']['pdf']['code'], 'COMPONENT_MISSING')
        self.assertEqual(report['components']['docx']['status'], 'missing')
        self.assertEqual(report['components']['ocr']['code'], 'DEPENDENCY_UNAVAILABLE')
        self.assertNotIn('private user source secret', json.dumps(report))

    def test_no_data_reads_no_subprocess_network_generation_or_recursive_scan(self):
        self.complete_files()
        self.file('data/private-user-secret.txt')
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('No component bytes read')), \
                patch.object(Path, 'read_text', side_effect=AssertionError('No private/raw config reads')), \
                patch.object(Path, 'rglob', side_effect=AssertionError('No recursive scan')):
            report = self.report()
        self.assertEqual(report['components']['pdf']['status'], 'available')
        self.assertNotIn('private-user-secret', json.dumps(report))
        self.assertFalse(hasattr(COMPONENTS, 'request'))

    def test_diagnostics_positive_allowlist_drops_all_private_extras(self):
        report = self.report()
        report['components']['local_model']['inventory'] = {'models': [{'name': 'private-model-title'}],
                                                           'token': 'secret-session-token', 'path': 'C:\\private-user\\data'}
        self.assertEqual(report['components']['local_model']['status'], 'not_checked')
        report.update(paths=['C:\\private-user\\data'], raw_logs='secret-session-token', filename='private-paper.pdf',
                      title='Private manuscript', counts={'patients': 99}, hostname='private-laptop')
        report['components']['pdf']['raw_error'] = 'private source failed'
        exported = diagnostics(report)
        self.assertEqual(set(exported), {'schema_version', 'app', 'os', 'components', 'languages'})
        self.assertEqual(set(exported['components']['pdf']), {'requirement', 'status', 'origin', 'code'})
        serialized = json.dumps(exported)
        for forbidden in ('private-user', 'secret-session-token', 'private-paper', 'Private manuscript', 'patients', 'private-laptop', 'private-model-title', 'private source'):
            self.assertNotIn(forbidden, serialized)

    def test_untrusted_identity_os_and_status_values_never_escape(self):
        with patch('installation_health.platform.system', return_value='Windows'), \
                patch('installation_health.platform.version', return_value='10.0.26300-private-host'):
            report = self.report()
        self.assertEqual(report['os'], {'family': 'Windows', 'version': 'unknown'})
        report['app']['version'] = '1.0.0-private-account'
        report['app']['build'] = 'secret-token'
        report['components']['pdf']['code'] = 'raw secret message'
        exported = diagnostics(report)
        self.assertEqual(exported['app'], {'version': 'unknown', 'build': 'unknown'})
        self.assertEqual(exported['components']['pdf']['code'], 'CHECK_FAILED')
        self.assertNotIn('private', json.dumps(exported))
        self.assertNotIn('secret', json.dumps(exported))

    def test_probe_os_error_sanitized_without_breaking_other_components(self):
        self.complete_files()
        def imported(name):
            if name == 'pymupdf':
                raise OSError('C:\\private-user\\missing-library.dll; token private-secret')
            return self.docx
        with patch('installation_health.importlib.import_module', side_effect=imported):
            report = check(self.root, app_version='1.0.0', app_build=self.build)
        self.assertEqual(report['components']['pdf']['status'], 'error')
        self.assertEqual(report['components']['pdf']['code'], 'CHECK_FAILED')
        self.assertEqual(report['components']['docx']['status'], 'available')
        self.assertNotIn('private-user', json.dumps(report))

    def test_failed_external_language_and_install_marker_checks_stay_unknown(self):
        real_file = health._file
        def file_probe(path):
            if path == self.root / 'INSTALL_RECEIPT.json' or path == self.root / 'outside-tessdata/eng.traineddata':
                return 'error'
            return real_file(path)
        with patch.object(health, '_file', side_effect=file_probe):
            report = self.report()
        self.assertEqual(report['components']['python']['status'], 'error')
        self.assertEqual(report['components']['python']['code'], 'CHECK_FAILED')
        self.assertEqual(report['languages']['eng']['status'], 'error')
        self.assertEqual(report['languages']['eng']['code'], 'CHECK_FAILED')

    def test_current_release_candidate_version_roundtrip_without_metadata(self):
        report = self.report()
        report['app']['version'] = CURRENT_VERSION
        self.assertEqual(diagnostics(report)['app']['version'], CURRENT_VERSION)
        report['app']['version'] = '1.0.0-rc.1'
        self.assertEqual(diagnostics(report)['app']['version'], '1.0.0-rc.1')
        for private in ('1.0.0-private-user', '1.0.0-rc.1+private-machine', '1.0.0-rc.secret'):
            report['app']['version'] = private
            self.assertEqual(diagnostics(report)['app']['version'], 'unknown')


if __name__ == '__main__':
    unittest.main()
