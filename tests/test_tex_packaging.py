import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('tex_builder_test', ROOT / 'scripts/build_installer.py')
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)
PACKAGE_REVISIONS = {'amsmath': 61041, 'fancyhdr': 57672, 'fontspec': 61617,
                     'geometry': 61719, 'graphics': 61315, 'hyperref': 62142,
                     'hyph-utf8': 61719, 'latex': 61232, 'lineno': 61719,
                     'setspace': 24881, 'tex-gyre': 48058, 'unicode-data': 60516}
REQUIRED_SOURCES = {
    'work/tex-components/tectonic-0.17.0-source.tar.gz',
    'work/tex-components/tectonic-0.17.0-windows-msvc.zip',
    'work/tex-components/texlive-source-receipt.json',
} | {'work/tex-components/' + name + '.' + kind + '.r' + str(revision) + '.tar.xz'
     for name, revision in PACKAGE_REVISIONS.items()
     for kind in (('doc',) if name in ('setspace', 'unicode-data') else ('doc', 'source'))}
REQUIRED_SOURCES.update('work/tex-components/' + name for name in (
    'amsfonts.doc.r61937.tar.xz', 'amsfonts.source.r61937.tar.xz', 'amsfonts.r61937.tar.xz',
    'cm.doc.r57963.tar.xz', 'cm.r57963.tar.xz', 'lm.doc.r61719.tar.xz', 'lm.r61719.tar.xz'))


class TexPackaging(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.original = json.loads((ROOT / 'vendor/tex/receipt.json').read_text())
        self.rows = []
        for original in self.original['payload_files']:
            name = original['path']
            content = ('synthetic bytes: ' + name).encode()
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            self.rows.append({'path': name, 'bytes': len(content),
                              'sha256': hashlib.sha256(content).hexdigest()})
        self.patcher = patch.object(builder, 'ROOT', self.root)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def source(self, rows=None):
        return {'vendor/tex/receipt.json': json.dumps({'payload_files': self.rows if rows is None else rows}).encode()}

    def test_installed_paths_match_fixed_runtime_and_legal_mapping(self):
        files = self.source()
        builder.tex_payload(files)
        self.assertIn('tools/tectonic/tectonic.exe', files)
        self.assertIn('vendor/tex/kosh-tex.zip', files)
        for row in self.rows:
            if row['path'].startswith('work/tex-components/'):
                self.assertIn('legal/tex/' + Path(row['path']).name, files)
        self.assertFalse(any(name.startswith('work/') for name in files))

    def test_duplicate_and_traversal_rejected(self):
        with self.assertRaises(ValueError):
            builder.tex_payload(self.source(self.rows + [self.rows[0]]))
        row = dict(self.rows[0], path='work/tex-components/../../outside')
        with self.assertRaises(ValueError):
            builder.tex_payload(self.source([row] + self.rows[1:]))

    def test_hash_and_size_rejected(self):
        for change in ({'sha256': '0' * 64}, {'bytes': self.rows[0]['bytes'] + 1}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                builder.tex_payload(self.source([dict(self.rows[0], **change)] + self.rows[1:]))

    def test_required_compiler_bundle_license_and_audit_cannot_be_omitted(self):
        for name in ('tools/tectonic/tectonic.exe', 'vendor/tex/kosh-tex.zip',
                     'vendor/tex/LICENSE.tectonic', 'work/tex-components/source-version-audit.json'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                builder.tex_payload(self.source([row for row in self.rows if row['path'] != name]))

    def test_matching_source_archives_and_origin_receipt_cannot_be_omitted(self):
        self.assertTrue(REQUIRED_SOURCES.issubset({row['path'] for row in self.original['payload_files']}))
        for name in sorted(REQUIRED_SOURCES):
            with self.subTest(name=name), self.assertRaises(ValueError):
                builder.tex_payload(self.source([row for row in self.rows if row['path'] != name]))

    def test_conflicting_legal_destination_rejected(self):
        files = self.source()
        files['legal/tex/tectonic-0.17.0-source.tar.gz'] = b'unrelated bytes'
        with self.assertRaises(ValueError):
            builder.tex_payload(files)


if __name__ == '__main__':
    unittest.main()
