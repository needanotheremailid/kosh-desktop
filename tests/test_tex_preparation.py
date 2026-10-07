import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('tex_preparation', ROOT / 'scripts/fetch_tex_components.py')
preparation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preparation)


class LatinModernPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.fonts = {'lmroman9-regular.otf': b'original regular font',
                      'lmroman9-italic.otf': b'original italic font'}
        self.resources = {name: b'\\UnicodeFontFile{lmroman9-regular}{}\\UnicodeFontFile{lmroman9-italic}{}'
                          for name in ('tulmr.fd', 'tulmss.fd', 'tulmtt.fd')}
        self.prepare_archive(self.fonts)

    def prepare_archive(self, fonts):
        path = self.root / 'lm.r61719.tar.xz'
        with tarfile.open(path, 'w:xz') as archive:
            for name, content in fonts.items():
                member = tarfile.TarInfo('fonts/opentype/public/lm/' + name)
                member.size = len(content)
                archive.addfile(member, io.BytesIO(content))
        receipt = {'files': [{'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}]}
        (self.root / 'receipt.json').write_text(json.dumps(receipt), encoding='utf-8')

    def test_absent_optical_sizes_are_supplied_with_exact_source_provenance(self):
        additions, receipt = preparation.latin_modern_resources(self.resources, self.root)
        self.assertEqual(additions, self.fonts)
        self.assertEqual(receipt['referenced_fonts'], 2)
        self.assertEqual(receipt['added_fonts'], ['lmroman9-italic.otf', 'lmroman9-regular.otf'])
        self.assertEqual(receipt['matched_files'][0]['original_member'],
                         'fonts/opentype/public/lm/lmroman9-italic.otf')

    def test_incomplete_family_without_reviewed_sources_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            preparation.latin_modern_resources(self.resources)

    def test_source_receipt_mismatch_is_refused(self):
        (self.root / 'lm.r61719.tar.xz').write_bytes(b'changed source')
        with self.assertRaisesRegex(ValueError, 'receipt mismatch'):
            preparation.latin_modern_resources(self.resources, self.root)

    def test_missing_source_font_and_mixed_cached_font_are_refused(self):
        self.prepare_archive({'lmroman9-regular.otf': self.fonts['lmroman9-regular.otf']})
        with self.assertRaisesRegex(ValueError, 'omits font'):
            preparation.latin_modern_resources(self.resources, self.root)
        self.prepare_archive(self.fonts)
        self.resources['lmroman9-regular.otf'] = b'different cached font'
        with self.assertRaisesRegex(ValueError, 'differs from reviewed source'):
            preparation.latin_modern_resources(self.resources, self.root)


if __name__ == '__main__':
    unittest.main()
