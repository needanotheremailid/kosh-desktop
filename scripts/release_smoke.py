"""Check a fresh installed package with synthetic inputs and no provider calls."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import zipfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--install-dir', type=Path, required=True)
args = parser.parse_args()
root = args.install_dir.resolve()
assert Path(sys.executable).resolve().is_relative_to(root / 'runtime')
assert sys.flags.ignore_environment and sys.flags.no_user_site
assert not (root / 'data').exists(), 'Use a fresh unlaunched installation.'
manifest = json.loads((root / 'package-manifest.json').read_text(encoding='utf-8-sig'))
for row in manifest['files']:
    path = (root / row['path']).resolve()
    assert path.is_relative_to(root) and path.is_file()
    assert path.stat().st_size == row['size']
    assert hashlib.sha256(path.read_bytes()).hexdigest() == row['sha256'], row['path']
sys.path.insert(0, str(root))
import backend, csl_engine, csl_styles, manuscript, manuscript_templates, tex_compile, word_citations
import pymupdf, docx, lxml
for module in (backend, csl_engine, csl_styles, manuscript, manuscript_templates,
               tex_compile, word_citations, pymupdf, docx, lxml):
    assert Path(module.__file__).resolve().is_relative_to(root), module.__name__
with tempfile.TemporaryDirectory(prefix='kosh-release-smoke-') as temporary:
    store = backend.Store(Path(temporary) / 'data')
    try:
        assert store.dispatch('GET', '/api/workspaces', {})['workspaces'] == []
    finally:
        store.close()
    library = csl_styles.StyleLibrary(Path(temporary) / 'styles')
    assert len(library.list_locales()) == 63
    bundle = library.resolve_bundle('chicago-note')
    item = {'id':'a','type':'book','title':'Synthetic widgets','author':[{'family':'Doe','given':'Jane'}], 'issued':{'date-parts':[[2024]]}}
    formatted = csl_engine.render([item], [['a']], **{key:bundle[key] for key in ('style_xml','language','locales')})
    assert formatted['style_class'] == 'note' and 'Synthetic widgets' in formatted['citations'][0]
markdown = '# Synthetic release check\n\n## Findings\n\n'+r'$$\begin{pmatrix}1 & 2\\3 & 4\end{pmatrix}\quad\int_0^1x^2\,dx=\frac13,\quad\mathbb{R}+\mathfrak{g}$$'
options = manuscript_templates.validate_template({'profile':'research','authors':'Synthetic Author'})
markdown = manuscript_templates.template_markdown(markdown, options, 'Synthetic release check')
protected, equations = tex_compile.prepare_math(markdown)
tex = tex_compile.restore_math(manuscript.render_latex(protected), equations)
tex = manuscript_templates.apply_tex_template(tex, options, 'Synthetic release check')
pdf = tex_compile.compile_tex(tex)
with pymupdf.open(stream=pdf, filetype='pdf') as document:
    text = '\n'.join(page.get_text() for page in document)
    assert 'Synthetic release check' in text and len(document) >= 2
    pages = len(document)
source = {'id':'a'*32,'kind':'pdf','pages':1,'name':'synthetic.pdf',
          'metadata':{'type':'journal_article','title':'Synthetic widgets','year':'2024'}}
word = word_citations.render_live_docx('Claim [[source:'+'a'*32+':1]].', [source])
with zipfile.ZipFile(io.BytesIO(word)) as archive:
    assert b'CITATION' in archive.read('word/document.xml')
    assert b'BIBLIOGRAPHY' in archive.read('word/document.xml')
    assert b'Synthetic widgets' in archive.read('customXml/item1.xml')
print(json.dumps({'ok':True,'build':manifest['build'],'verified_payload_files':len(manifest['files']),
                  'bundled_origins':True,'empty_library':True,'csl_locales':63,
                  'offline_compiled_pdf_pages':pages,'native_word_fields':True,
                  'scope':'Fresh installed runtime checks; synthetic inputs; no desktop UI or native Word automation.'}))
