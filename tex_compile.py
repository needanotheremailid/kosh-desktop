"""Offline compilation of Kosh-generated TeX, never arbitrary imported documents.

Tectonic's untrusted mode disables shell escape, NOT filesystem access. The
caller must generate document structure and escape all prose. Only allowlisted
math can be restored as executable TeX. This is not an OS security sandbox.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parent
COMPILER = ROOT / 'tools' / 'tectonic' / 'tectonic.exe'
BUNDLE = ROOT / 'vendor' / 'tex' / 'kosh-tex.zip'
MAX_SOURCE = 2_000_000
MAX_ASSETS = 47_000_000
MAX_SECONDS = 60
MAX_DIAGNOSTICS = 8_000_000


class TexError(ValueError):
    pass


MATH_COMMANDS = frozenset('frac dfrac tfrac sqrt sum prod coprod int iint iiint oint lim log ln exp sin cos tan cot sec csc sinh cosh tanh min max inf sup det gcd mod bmod pmod binom dbinom tbinom overline underline hat widehat bar vec dot ddot tilde widetilde acute grave breve check mathrm mathit mathbf mathsf mathtt mathcal mathbb mathfrak text operatorname left right middle big Big bigg Bigg bigl bigr Bigl Bigr biggl biggr Biggl Biggr alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota kappa lambda mu nu xi pi varpi rho varrho sigma varsigma tau upsilon phi varphi chi psi omega Gamma Delta Theta Lambda Xi Pi Sigma Upsilon Phi Psi Omega infty partial nabla ell hbar imath jmath forall exists neg in notin subset supset subseteq supseteq cup cap emptyset varnothing land lor implies iff to mapsto rightarrow leftarrow leftrightarrow Rightarrow Leftarrow Leftrightarrow uparrow downarrow le leq ge geq neq ne approx sim simeq equiv propto times cdot div pm mp circ bullet star ast ldots cdots vdots ddots dots lbrace rbrace langle rangle vert Vert lvert rvert lVert rVert quad qquad thinspace medspace thickspace displaystyle textstyle scriptstyle scriptscriptstyle limits nolimits underbrace overbrace underset overset substack begin end'.split())
MATH_ENVIRONMENTS = frozenset('aligned alignedat gathered cases matrix pmatrix bmatrix Bmatrix vmatrix Vmatrix smallmatrix split'.split())


def validate_math(expression):
    if not isinstance(expression, str) or len(expression) > 20_000:
        raise TexError('Equation must contain at most 20,000 characters.')
    if '%' in expression or '^^' in expression or '\x00' in expression or any(ord(char) < 32 and char not in '\n\r\t' for char in expression):
        raise TexError('Comments, character rewriting and control characters are not allowed in equations.')
    for match in re.finditer(r'\\([A-Za-z]+|.)', expression, re.S):
        command = match[1]
        if command not in MATH_COMMANDS and command not in '{}_|,;:! \\#&$':
            raise TexError('Unsupported equation command: \\' + command)
    environments = []
    for match in re.finditer(r'\\(begin|end)\s*\{([^{}]*)\}', expression):
        action, name = match.groups()
        if name not in MATH_ENVIRONMENTS:
            raise TexError('Unsupported equation environment.')
        if action == 'begin':
            environments.append(name)
        elif not environments or environments.pop() != name:
            raise TexError('Equation environments are not balanced.')
    if environments:
        raise TexError('Equation environments are not balanced.')
    # Environment commands must have a literal name, preventing token tricks.
    stripped = re.sub(r'\\(?:begin|end)\s*\{[^{}]*\}', '', expression)
    if re.search(r'\\(?:begin|end)\b', stripped):
        raise TexError('Equation environment names must be literal.')
    return expression


def prepare_math(markdown):
    r"""Replace explicit $$…$$ and \(…\)/\[…\] math before prose escaping."""
    replacements = {}
    prefix = 'KOSHMATH' + uuid.uuid4().hex.upper()
    pattern = re.compile(r'\$\$(.*?)\$\$|\\\[(.*?)\\\]|\\\((.*?)\\\)|(?<![\\$])\$(?!\$)([^\n$]+?)(?<!\\)\$(?!\$)', re.S)
    def replace(match):
        expression = next(value for value in match.groups() if value is not None)
        validate_math(expression)
        sentinel = prefix + str(len(replacements)) + 'END'
        display = match[3] is None and match[4] is None
        opening, closing = ('$', '$') if match[4] is not None else (('\\[', '\\]') if display else ('\\(', '\\)'))
        replacements[sentinel] = opening + expression + closing
        return sentinel
    # Preserve code as literal source even when it contains math delimiters.
    code = re.compile(r'(^[ \t]*(`{3,}|~{3,})[^\n]*\n.*?^[ \t]*\2[ \t]*$)|(`+)[^\n]*?\3', re.M | re.S)
    parts = []
    start = 0
    for match in code.finditer(markdown):
        parts.extend([pattern.sub(replace, markdown[start:match.start()]), match[0]])
        start = match.end()
    parts.append(pattern.sub(replace, markdown[start:]))
    return ''.join(parts), replacements


def restore_math(tex, replacements):
    for sentinel, expression in replacements.items():
        tex = tex.replace(sentinel, expression)
    return tex


def compiler_status():
    ready = COMPILER.is_file() and BUNDLE.is_file()
    return {'ready': ready, 'engine': 'Tectonic 0.17.0', 'offline': True,
            'message': 'Bundled compiler ready.' if ready else 'Bundled TeX compiler or resource bundle is missing.'}


def compile_tex(source, assets=None):
    """Return PDF bytes for trusted generated source; assets are relative files.

    This API is intentionally internal: no arbitrary .tex upload route may call
    it. Runtime never searches PATH or downloads missing packages.
    """
    if not isinstance(source, str) or len(source.encode('utf-8')) > MAX_SOURCE:
        raise TexError('Generated TeX exceeds the compilation limit.')
    assets = assets or {}
    total = 0
    for name, content in assets.items():
        if not re.fullmatch(r'figures/[A-Za-z0-9_.-]+\.(?:png|jpg|jpeg)', name) or '..' in name or not isinstance(content, bytes):
            raise TexError('Invalid generated figure asset.')
        total += len(content)
    if total > MAX_ASSETS:
        raise TexError('Generated figures exceed the compilation limit.')
    if not compiler_status()['ready']:
        raise TexError(compiler_status()['message'])
    with tempfile.TemporaryDirectory(prefix='kosh-tex-') as folder:
        job = Path(folder)
        (job / 'document.tex').write_text(source, encoding='utf-8')
        for name, content in assets.items():
            target = job / name
            target.parent.mkdir(exist_ok=True)
            target.write_bytes(content)
        # Windows known-folder APIs require the real profile locations even
        # with an explicit isolated compiler cache. No PATH/provider secrets.
        env = {key: value for key, value in os.environ.items()
               if key.upper() in ('SYSTEMROOT', 'WINDIR', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA')}
        env.update({'TECTONIC_UNTRUSTED_MODE': '1', 'TECTONIC_CACHE_DIR': str(job / 'cache'),
                    'TEMP': folder, 'TMP': folder})
        # A drive-letter path is parsed as a URI scheme by Tectonic on Windows.
        command = [str(COMPILER), '--untrusted', '--only-cached', '--bundle', BUNDLE.as_uri(),
                   '--reruns', '1', '--outdir', folder, 'document.tex']
        try:
            # Diagnostics stay inside the disposable job, never app logs/chat.
            # --print makes missing-glyph diagnostics observable rather than
            # accepting a PDF that has silently omitted supplied characters.
            command.append('--print')
            diagnostics = job / 'diagnostics.txt'
            with diagnostics.open('wb') as stream:
                process = subprocess.Popen(command, cwd=folder, env=env, stdin=subprocess.DEVNULL,
                                           stdout=stream, stderr=subprocess.STDOUT,
                                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                deadline = time.monotonic() + MAX_SECONDS
                try:
                    while process.poll() is None:
                        if time.monotonic() >= deadline:
                            raise TexError('TeX compilation exceeded 60 seconds.')
                        if diagnostics.stat().st_size > MAX_DIAGNOSTICS:
                            raise TexError('TeX compilation produced excessive diagnostics. Simplify the document.')
                        time.sleep(0.05)
                finally:
                    if process.poll() is None:
                        process.kill()
                    process.wait()
        except OSError as exc:
            raise TexError('Bundled TeX compiler could not start.') from exc
        output = job / 'document.pdf'
        if diagnostics.stat().st_size > MAX_DIAGNOSTICS:
            raise TexError('TeX compilation produced excessive diagnostics. Simplify the document.')
        messages = diagnostics.read_text(encoding='utf-8', errors='replace').lower()
        if 'missing character:' in messages or 'missing glyph' in messages:
            raise TexError('The bundled TeX fonts cannot render one or more characters. Use Word or HTML for this document.')
        if process.returncode or not output.is_file():
            raise TexError('TeX compilation failed. Check equation syntax and supported commands.')
        result = output.read_bytes()
        if not result.startswith(b'%PDF-') or len(result) > 64_000_000:
            raise TexError('TeX compiler did not produce a valid bounded PDF.')
        return result
