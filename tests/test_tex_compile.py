import unittest
from unittest.mock import patch
import subprocess
from tex_compile import TexError, prepare_math, restore_math, validate_math
import tex_compile


class MathBoundaryTests(unittest.TestCase):
    def test_advanced_math_roundtrip(self):
        expression = r'\begin{aligned} a &= \sum_{i=1}^{n} i \\ b &= \int_0^1 x^2\,dx \end{aligned}'
        text, replacements = prepare_math('Before\n$$' + expression + '$$\nAfter')
        self.assertNotIn('aligned', text)
        self.assertIn(r'\[' + expression + r'\]', restore_math(text, replacements))

    def test_denies_execution_and_indirect_primitives(self):
        for expression in (r'\input{../secret}', r'\csname input\endcsname{x}',
                           r'\newcommand{\a}{x}', r'\write18{cmd}', 'x%hidden',
                           '^^5cinput{x}', r'\begin{document}x\end{document}'):
            with self.subTest(expression=expression), self.assertRaises(TexError):
                validate_math(expression)

    def test_plain_text_is_preserved(self):
        self.assertEqual(prepare_math('Costs $5 and normal prose.'), ('Costs $5 and normal prose.', {}))

    def test_inline_math_and_code_exclusion(self):
        text, mapping = prepare_math('Inline $x^2$ and `$$\\input{x}$$`\n```tex\n$$\\input{x}$$\n```\nEnd.')
        self.assertEqual(len(mapping), 1)
        self.assertIn('`$$\\input{x}$$`', text)
        self.assertIn('```tex\n$$\\input{x}$$\n```', text)
        self.assertIn('$x^2$', restore_math(text, mapping))

    def test_invalid_expression_fails_explicitly(self):
        with self.assertRaises(TexError):
            prepare_math(r'$$\unknown{x}$$')

    def test_asset_traversal_rejected_before_execution(self):
        with patch('tex_compile.subprocess.Popen') as run:
            with self.assertRaises(TexError):
                tex_compile.compile_tex('generated', {'figures/../../secret.png': b'x'})
            run.assert_not_called()

    def test_timeout_error_is_sanitized_and_offline_flags_are_fixed(self):
        with patch('tex_compile.compiler_status', return_value={'ready': True}), patch(
                'tex_compile.subprocess.Popen') as run, patch('tex_compile.time.monotonic', side_effect=[0, 61]):
            run.return_value.poll.return_value = None
            with self.assertRaisesRegex(TexError, '^TeX compilation exceeded 60 seconds.$'):
                tex_compile.compile_tex('generated')
            command = run.call_args.args[0]
            self.assertIn('--only-cached', command)
            self.assertIn('--untrusted', command)
            self.assertNotIn('PATH', run.call_args.kwargs['env'])
            run.return_value.kill.assert_called_once()
            run.return_value.wait.assert_called_once()
