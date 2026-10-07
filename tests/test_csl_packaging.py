import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('kosh_builder', ROOT / 'scripts/build_installer.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class CSLPackaging(unittest.TestCase):
    def test_payload_requires_matching_shipped_processor(self):
        with self.assertRaisesRegex(ValueError, 'CSL source'):
            builder.csl_payload({})

    def test_required_component_allowlist(self):
        for name in ('csl_engine.py', 'pdf_math.py', 'csl_styles.py', 'SIGNING.md', 'scripts/sign-release.ps1', 'vendor/csl/citeproc-LICENSE', 'vendor/csl/styles/apa.csl','word_citations.py','citation_notes.py','manuscript_templates.py','tex_compile.py','vendor/tex/receipt.json','vendor/tex/LICENSE.tectonic'):
            self.assertTrue(builder.source_allowed(name), name)
        self.assertFalse(builder.source_allowed('tools/node/node.exe'))


if __name__ == '__main__':
    unittest.main()
