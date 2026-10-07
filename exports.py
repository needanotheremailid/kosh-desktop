"""Original read-only manuscript/export composition over the current store.

Exports saved records only. No network, external-file reads, execution, data
mutation or inference of missing publication facts. Default documents contain
the manuscript and references; optional audit material is explicitly requested.
"""
from __future__ import annotations

import base64
import csv
import html
import io
import json
import re
import zipfile
from pathlib import Path
from datetime import datetime, timezone

from bibliography import export_csl_json, export_ris
from citations import CitationError, citation_key, normalized_doi, render_citations
from manuscript import ManuscriptError, inline_tokens, parse_markdown, render_docx, render_html, render_latex


class ExportError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message, self.status = message, status


FORMATS = {'md', 'docx', 'docxlive', 'pdf', 'texpdf', 'tex', 'texzip', 'bib', 'csv', 'ris', 'csljson', 'html', 'share'}
FIGURE_KINDS = {'png', 'jpg', 'jpeg', 'webp'}
LIMIT = 47 * 1024 * 1024
MIME = {'md': 'text/markdown; charset=utf-8', 'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'pdf': 'application/pdf', 'tex': 'application/x-tex; charset=utf-8', 'texzip': 'application/zip',
        'bib': 'application/x-bibtex; charset=utf-8', 'ris': 'application/x-research-info-systems; charset=utf-8',
        'csljson': 'application/vnd.citationstyles.csl+json; charset=utf-8', 'csv': 'text/csv; charset=utf-8',
        'html': 'text/html; charset=utf-8', 'share': 'application/zip'}
MIME.update(docxlive=MIME['docx'], texpdf='application/pdf')
CSS = '''body {font-family:serif; font-size:11pt; line-height:1.35; color:#222;}
h1 {font-size:22pt;} h2 {font-size:16pt;} h3 {font-size:13pt;}
p {margin:0 0 9pt;} table {border-collapse:collapse; width:100%; margin:10pt 0;}
th,td {border:1px solid #bbb; padding:5pt; vertical-align:top;} th {background:#eee;}
blockquote {border-left:2px solid #999; margin:10pt 15pt; padding-left:10pt;}
pre {white-space:pre-wrap; background:#f4f4f4; padding:8pt;} code {font-family:monospace;}
figure {margin:14pt 0; text-align:center; page-break-inside:avoid;}
img {max-width:100%; max-height:600px;} figcaption {font-size:10pt; margin-top:5pt;}
.math {font-family:serif;} .equation {text-align:center; margin:10pt;}
'''


def _heading(value):
    return re.sub(r'([\\*_\[\]`])', r'\\\1', str(value).replace('\r', ' ').replace('\n', ' '))


def _demote(markdown, amount):
    lines, fence = [], None
    for line in markdown.splitlines():
        marker = re.match(r'^\s*(`{3,}|~{3,})', line)
        if marker:
            if fence is None:
                fence = marker[1]
            elif marker[1][0] == fence[0] and len(marker[1]) >= len(fence):
                fence = None
            lines.append(line)
            continue
        heading = re.match(r'^(#{1,6})(\s+.*)$', line) if fence is None else None
        lines.append('#' * min(6, len(heading[1]) + amount) + heading[2] if heading else line)
    return '\n'.join(lines)


def _compose(snapshot, selected):
    notes = snapshot['notes']
    title = notes[0]['title'] if selected else snapshot['workspace']['title']
    lines = ['# ' + _heading(title), '']
    for note in notes:
        if not selected:
            lines.extend(['## ' + _heading(note['title']), ''])
        lines.extend([_demote(note['body'], 1 if selected else 2), ''])
    if snapshot['matrix']:
        lines.extend(['## Evidence matrix', ''])
        by_id = {document['id']: document for document in snapshot['documents']}
        for row in snapshot['matrix']:
            document = by_id.get(row['document_id'])
            name = document['name'] if document else '[source missing]'
            lines.extend(['### ' + _heading(name) + ' [[reference:' + row['document_id'] + ']]', ''])
            for field in ('question', 'design', 'findings', 'limitations'):
                if row.get(field):
                    lines.extend(['**' + field.title() + ':** ' + row[field], ''])
    return '\n'.join(lines).rstrip() + '\n'


def _bibliography_documents(documents, cited_ids=None):
    by_id = {document['id']: document for document in documents}
    candidates = [by_id[identifier] for identifier in cited_ids if identifier in by_id] if cited_ids is not None else documents
    seen, result = set(), []
    for document in candidates:
        if document['kind'] in FIGURE_KINDS:
            continue
        doi = normalized_doi(str(document['metadata'].get('doi', ''))).casefold()
        key = ('doi', doi) if doi else ('id', document['id'])
        if key not in seen:
            result.append(document)
            seen.add(key)
    return result


def _records(documents):
    result = []
    for document in documents:
        metadata = dict(document['metadata'])
        if metadata.get('doi'):
            metadata['doi'] = normalized_doi(str(metadata['doi'])) or metadata['doi']
        result.append({**metadata, 'id': citation_key(document['id'])})
    return result


def _bib_value(value, raw=False):
    escapes = {'\\': r'\textbackslash{}', '{': r'\{', '}': r'\}', '\r': ' ', '\n': ' '}
    if not raw:
        escapes.update({'&': r'\&', '%': r'\%', '#': r'\#', '_': r'\_', '$': r'\$', '~': r'\textasciitilde{}', '^': r'\textasciicircum{}'})
    return ''.join(escapes.get(char, char) for char in str(value))


def _bibtex(documents):
    kinds = {'journal_article': 'article', 'book': 'book', 'book_chapter': 'incollection', 'report': 'techreport', 'thesis': 'phdthesis'}
    output = []
    fields = {'title': 'title', 'year': 'year', 'doi': 'doi', 'url': 'url', 'journal': 'journal',
              'journal_abbreviation': 'shortjournal', 'volume': 'volume', 'issue': 'number', 'pages': 'pages',
              'publisher': 'publisher', 'publisher_place': 'address', 'booktitle': 'booktitle',
              'edition': 'edition', 'isbn': 'isbn', 'issn': 'issn', 'abstract': 'abstract'}
    for document in documents:
        metadata = document['metadata']
        values = []
        if metadata.get('author_list'):
            authors = []
            for author in metadata['author_list']:
                if author.get('literal'):
                    authors.append('{' + _bib_value(author['literal']) + '}')
                else:
                    authors.append(_bib_value(author.get('family', '')) + (', ' + _bib_value(author['given']) if author.get('given') else ''))
            values.append('  author = {' + ' and '.join(authors) + '}')
        elif metadata.get('authors'):
            values.append('  author = {{' + _bib_value(metadata['authors']) + '}}')
        for key, name in fields.items():
            if metadata.get(key):
                value = (normalized_doi(str(metadata[key])) or metadata[key]) if key == 'doi' else metadata[key]
                values.append('  ' + name + ' = {' + _bib_value(value, raw=key in {'doi', 'url'}) + '}')
        for key, name in {'editors': 'editor', 'institution': 'school' if metadata.get('type') == 'thesis' else 'institution', 'report_number': 'number', 'thesis_type': 'type'}.items():
            if metadata.get(key):
                values.append('  ' + name + ' = {' + _bib_value(metadata[key]) + '}')
        # Generic thesis metadata does not establish doctoral status. BibTeX
        # misc + explicit type retains that boundary rather than inventing it.
        kind = kinds.get(metadata.get('type'), 'misc')
        if metadata.get('type') == 'thesis':
            kind = 'misc'
            if not metadata.get('thesis_type'):
                values.append('  type = {Thesis}')
        output.append('@' + kind + '{' + citation_key(document['id']) + ',\n' + ',\n'.join(values) + '\n}')
    return ('\n\n'.join(output) + ('\n' if output else '')).encode('utf-8')


def _csv(snapshot, style, style_xml=None, language=None, locales=None):
    buffer = io.StringIO(newline='')
    writer = csv.writer(buffer)
    writer.writerow(['Source', 'Title', 'Authors', 'Year', 'DOI', 'Question', 'Design', 'Findings', 'Limitations'])
    by_id = {document['id']: document for document in snapshot['documents']}
    texts = [row.get(field, '') for row in snapshot['matrix'] for field in ('question', 'design', 'findings', 'limitations')]
    rendered = render_citations(texts, snapshot['documents'], style, style_xml=style_xml,language=language,locales=locales)['texts'] if texts else []
    for index, row in enumerate(snapshot['matrix']):
        document = by_id.get(row['document_id'])
        if document is None:
            raise ExportError('Evidence row references a source outside this workspace.')
        metadata = document['metadata']
        values = [document['name'], metadata.get('title', ''), metadata.get('authors', ''), metadata.get('year', ''), metadata.get('doi', ''), *rendered[index * 4:index * 4 + 4]]
        writer.writerow(["'" + value if str(value).lstrip().startswith(('=', '+', '-', '@')) else value for value in values])
    return ('\ufeff' + buffer.getvalue()).encode('utf-8')


def _image_targets(markdown):
    targets = []
    def inline(text):
        def walk(tokens):
            for token in tokens:
                if token['type'] == 'image' and token['target'].startswith('kosh-asset:'):
                    targets.append(token['target'])
                if token.get('children'):
                    walk(token['children'])
        walk(inline_tokens(text))
    def blocks(values):
        for block in values:
            if block['type'] in {'heading', 'paragraph'}:
                inline(block['text'])
            elif block['type'] == 'list':
                for item in block['items']:
                    inline(item['text'])
                    blocks(item['children'])
            elif block['type'] == 'quote':
                blocks(block['children'])
            elif block['type'] == 'table':
                for row in [block['header'], *block['rows']]:
                    for cell in row:
                        inline(cell)
    blocks(parse_markdown(markdown))
    return list(dict.fromkeys(targets))


def _figures(store, markdown, workspace_id):
    figures, total = {}, 0
    for target in _image_targets(markdown):
        match = re.fullmatch(r'kosh-asset:([a-f0-9]{32})', target)
        if not match:
            raise ExportError('Managed figure identifier is invalid.')
        document = store._document(match[1], workspace_id)
        if document['kind'] not in FIGURE_KINDS:
            raise ExportError('Managed figure target must be an imported PNG, JPEG or WebP image.')
        data = store._bytes(document)
        total += len(data)
        if total > LIMIT:
            raise ExportError('Referenced figures exceed the 47 MiB export bound.', 413)
        extension = 'jpg' if document['kind'] == 'jpeg' else document['kind']
        figures[target] = {'id': document['id'], 'bytes': data, 'extension': extension,
                           'mime': 'image/jpeg' if extension == 'jpg' else 'image/' + extension}
    return figures


def _png_figures(figures):
    import pymupdf
    values = {}
    for target, figure in figures.items():
        data = figure['bytes']
        extension = figure['extension']
        if extension == 'webp':
            try:
                data = pymupdf.Pixmap(data).tobytes('png')
            except Exception as error:
                raise ExportError('Managed WebP figure could not be decoded.') from error
            extension = 'png'
        values[target] = {**figure, 'bytes': data, 'extension': extension, 'path': 'figures/' + figure['id'] + '.' + extension}
    return values


def _html_document(markdown, title, image_url, css='', language='en'):
    return '<!doctype html>\n<html lang="'+html.escape(language,quote=True)+'"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>' + html.escape(title) + '</title><style>' + CSS + css + '</style></head><body>' + render_html(markdown, image_url) + '</body></html>'


def _pdf_typeset_math(document_html, archive):
    """Reserve Story layout rectangles; draw supported math as PDF vectors."""
    import pymupdf
    from pdf_math import layout_math
    equations = {}
    pixel = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 1, 1), True)
    pixel.clear_with(255)
    pixel.set_alpha(bytes([0]))
    archive.add(pixel.tobytes('png'), 'pdf-math-reserve.png')
    def replace(match):
        opening = match[0].split('>', 1)[0]
        original = re.search(r'\baria-label="([^"]*)"', opening)
        if original is None:
            raise ExportError('PDF equation has no retained source notation; output was refused.')
        display = 'display="block"' in opening
        try:
            formula = layout_math(match[0])
        except (ValueError, RecursionError):
            literal = '<code>Equation notation: ' + html.escape(html.unescape(original[1]), quote=False) + '</code>'
            return '<div class="equation">' + literal + '</div>' if display else literal
        identifier = 'pdf-equation-' + str(len(equations))
        equations[identifier] = formula
        scale = min(1, 475/formula.width, 700/formula.height)
        image = ('<img id="' + identifier + '" src="pdf-math-reserve.png" style="width:'
                 + str(formula.width*scale) + 'pt;height:' + str(formula.height*scale)
                 + 'pt;vertical-align:-' + str((0 if display else formula.descent)*scale) + 'pt">')
        if display:
            return '<div class="equation">' + image + '</div>'
        # Story shifts the image baseline without extending its line descent.
        # An explicit line height protects the following prose from overlap.
        return '<span style="line-height:' + str((formula.height+2*formula.descent)*scale) + 'pt">' + image + '</span>'
    return re.sub(r'<math\b[^>]*>.*?</math>', replace, document_html, flags=re.S), equations


def _pdf(markdown, title, figures, template=None):
    import pymupdf
    archive = pymupdf.Archive()
    for figure in figures.values():
        archive.add(figure['bytes'], figure['path'])
    from manuscript_templates import template_css
    text, equations = _pdf_typeset_math(_html_document(markdown, title, lambda target: '/' + figures[target]['path'] if target in figures else None, template_css(template) if template else ''), archive)
    for figure in figures.values():
        text = text.replace('src="/' + figure['path'] + '"', 'src="' + figure['path'] + '"')
    # Story decodes entities twice in text nodes. Our generated HTML has no
    # literal '<' or '>' in text/attributes: user text is already escaped.
    # Add one text-only escape layer, preserving tags, asset paths and links.
    text = re.sub(r'>([^<]*)', lambda match: '>' + match[1].replace('&', '&amp;'), text)
    story = pymupdf.Story(text, archive=archive)
    def rectangle(number, filled):
        if number >= 500:
            raise ExportError('PDF exceeds the 500-page export bound; no output was published.', 413)
        active=template and template['profile']!='none'
        width,height=(612,792) if active and template['page_size']=='letter' else (595,842)
        margin=template['margin_mm']*72/25.4 if active else 48
        page = pymupdf.Rect(0, 0, width, height)
        return page, pymupdf.Rect(margin, margin, width-margin, height-margin), None
    # Story's element-position callback reports inline boxes before their final
    # baseline shift. Read actual emitted image transforms instead. Pair every
    # image in source order, including managed figures, and refuse incomplete
    # placement rather than publishing missing/misplaced equations.
    image_ids = []
    for match in re.finditer(r'<img\b[^>]*>', text):
        identifier = re.search(r'\bid="([^"]*)"', match[0])
        image_ids.append(identifier[1] if identifier and identifier[1] in equations else None)
    document = story.write_with_links(rectangle)
    try:
        if equations:
            placements = [(page.number, pymupdf.Rect(image['bbox'])) for page in document for image in page.get_image_info()]
            if len(placements) != len(image_ids):
                raise ExportError('PDF equation placement is incomplete; output was refused.')
            for identifier, (page_number, bounds) in zip(image_ids, placements):
                if identifier:
                    equations[identifier].draw(document[page_number], bounds)
        if template and template['profile']!='none' and template['page_numbers']:
            for page in document: page.insert_text((page.rect.width-55,page.rect.height-25),str(page.number+1),fontsize=9)
        return document.tobytes(garbage=3, deflate=True)
    finally:
        document.close()


def _tex_literal(value):
    escapes = {'\\': r'\textbackslash{}', '{': r'\{', '}': r'\}', '&': r'\&', '%': r'\%', '$': r'\$', '#': r'\#', '_': r'\_', '~': r'\textasciitilde{}', '^': r'\textasciicircum{}'}
    return ''.join(escapes.get(char, char) if ord(char) >= 32 else ' ' for char in value)


def _tex_bundle(markdown, figures):
    from manuscript import _latex_blocks
    substitutions = {}
    # Match each complete image before checking its managed target. A broad
    # caption can contain brackets, but cannot consume an earlier external
    # image or the prose between images while searching for a managed target.
    pattern = re.compile(r'!\[([^\r\n]*?)\]\(([^)\r\n]*)\)')
    def replacement(match):
        figure = figures.get(match[2])
        if figure is None:
            return match[0]
        sentinel = 'KOSHFIGURETOKEN' + figure['id'] + 'TOKEN'
        while sentinel in markdown or sentinel in substitutions:
            sentinel += 'X'
        substitutions[sentinel] = '\n'.join([r'\begin{figure}[htbp]', r'\centering', r'\includegraphics[width=0.9\linewidth]{' + figure['path'] + '}', r'\caption{' + _tex_literal(match[1]) + '}', r'\end{figure}'])
        return sentinel
    def semantic_text(value):
        # Image syntax inside inline code is literal, matching the shared AST.
        pieces = re.split(r'(`+.*?`+)', value)
        return ''.join(piece if piece.startswith('`') else pattern.sub(replacement, piece) for piece in pieces)
    def visit(blocks):
        for block in blocks:
            if block['type'] in {'heading', 'paragraph'}:
                block['text'] = semantic_text(block['text'])
            elif block['type'] == 'list':
                for item in block['items']:
                    item['text'] = semantic_text(item['text'])
                    visit(item['children'])
            elif block['type'] == 'quote':
                visit(block['children'])
            elif block['type'] == 'table':
                block['header'] = [semantic_text(cell) for cell in block['header']]
                block['rows'] = [[semantic_text(cell) for cell in row] for row in block['rows']]
    blocks = parse_markdown(markdown)
    visit(blocks)
    text = render_latex('')
    text = text.replace(r'\end{document}', '\n'.join(_latex_blocks(blocks)) + '\n' + r'\end{document}', 1)
    text = text.replace(r'\usepackage{fontspec}', r'\usepackage{fontspec}' + '\n' + r'\usepackage{graphicx}', 1)
    for sentinel, figure_tex in substitutions.items():
        text = text.replace(sentinel, figure_tex)
    return text


def _zip(entries):
    if sum(len(data) for _, data in entries) > LIMIT:
        raise ExportError('Portable export exceeds the 47 MiB bound.', 413)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return buffer.getvalue()


def _reading_readme(style):
    names = {'vancouver': 'Vancouver', 'apa': 'APA', 'ieee': 'IEEE'}
    return ('Kosh portable reading copy\n\nReading copy, not a restorable workspace backup.\n'
            'Bibliographic metadata is unverified. Check it against each publication.\n'
            'Exported at: ' + datetime.now(timezone.utc).isoformat(timespec='seconds') + '\n'
            'Citation style: ' + names.get(style, 'Imported journal CSL style') + ' (CSL processor)\n\n'
            'Extract the whole ZIP and open index.html locally. Keep the figures folder beside it.\n'
            'Review the manuscript and permissions before sharing. This bundle excludes app runtime and original source-paper files.\n').encode('utf-8')


def export_workspace(store, query):
    format_ = query.get('format', 'md')
    style = query.get('citation_style', 'vancouver')
    from csl_styles import StyleLibrary, StyleError
    from manuscript_templates import validate_template, template_markdown, template_css, apply_docx_template, apply_tex_template, apply_html_template
    from citation_notes import apply_docx_notes, markdown_notes, html_notes, tex_notes
    from tex_compile import prepare_math, restore_math, compile_tex, TexError
    from word_citations import render_live_docx, WordCitationError
    try:
        template=query.get('template',{})
        if isinstance(template,str):template=json.loads(template)
        template=validate_template(template)
        library=StyleLibrary(getattr(store,'root',Path(__file__).resolve().parent/'vendor'))
        bundle=library.resolve_bundle('vancouver' if format_=='docxlive' else style,query.get('citation_language') or None)
        style_xml=bundle['style_xml']
        language,locales=bundle['language'],bundle['locales']
    except (ValueError, OSError) as error:
        raise ExportError(str(error)) from error
    note_placement=query.get('note_placement','footnote')
    if note_placement not in {'footnote','endnote'}:raise ExportError('Choose footnote or endnote placement.')
    if format_ not in FORMATS:
        raise ExportError('Choose Markdown, DOCX, PDF, LaTeX, TeX bundle, BibTeX, RIS, CSL JSON, CSV, HTML or portable HTML bundle.')
    audit = query.get('audit', '0')
    if audit not in {'0', '1'}:
        raise ExportError('Export audit must be 0 or 1.')
    snapshot = store._snapshot(query.get('workspace_id'), include_history=False)
    selected = bool(query.get('note_id'))
    if selected:
        notes = [note for note in snapshot['notes'] if note['id'] == query['note_id']]
        if not notes:
            raise ExportError('Draft not found in this workspace.', 404)
        snapshot['notes'], snapshot['matrix'] = notes, []
    markdown = _compose(snapshot, selected)
    try:
        citation_result = render_citations([markdown], snapshot['documents'], style, style_xml=style_xml,language=language,locales=locales,note_mode=True)
    except CitationError as error:
        raise ExportError(str(error)) from error
    bibliography = _bibliography_documents(snapshot['documents'], citation_result['cited_ids'] if selected else None)
    if format_ in {'bib', 'ris', 'csljson'}:
        records = _records(bibliography)
        data = _bibtex(bibliography) if format_ == 'bib' else (export_ris(records) if format_ == 'ris' else export_csl_json(records)).encode('utf-8')
    elif format_ == 'csv':
        data = _csv(snapshot, style, style_xml,language,locales)
    else:
        # Validate only originals actually cited by this manuscript. An
        # unrelated missing managed original cannot block a selected export.
        known = {document['id'] for document in snapshot['documents']}
        mentioned = set(re.findall(r'\[\[(?:source|reference):([a-f0-9]{32})(?::\d+)?\]\]', markdown)) & known
        for identifier in mentioned | set(citation_result['cited_ids']):
            store._bytes(store._document(identifier, snapshot['workspace']['id']))
        raw_markdown=markdown
        markdown = citation_result['texts'][0].rstrip() + '\n'
        if citation_result['references']:
            markdown += '\n## References\n\n' + '\n\n'.join(citation_result['references']) + '\n'
        if audit == '1':
            markdown += '\n## Export review notes\n\n'
            markdown += '\n\n'.join(citation_result['warnings']) or 'Bibliographic metadata requires checking against the publication.'
            markdown += '\n\n### Evidence locations\n\n'
            locator_documents = {document['id']: document for document in snapshot['documents']}
            for locator in citation_result['evidence_locators']:
                unit = 'PDF p.' if locator['kind'] == 'pdf' else 'text unit'
                markdown += '- [' + locator['label'] + '] ' + locator['document_id'] + ': ' + unit + ' ' + str(locator['page']) + '\n'
                source = locator_documents[locator['document_id']]
                provenance = source['metadata'].get('provenance', '')
                if provenance:
                    markdown += '  - Source provenance: ' + _heading(provenance) + '\n'
            if citation_result['document_references']:
                markdown += '\n### Document references\n\n'
                for reference in citation_result['document_references']:
                    markdown += '- [' + reference['label'] + '] ' + reference['document_id'] + ': document-level reference; no source location supplied.\n'
        figures = _figures(store, markdown, snapshot['workspace']['id'])
        title = snapshot['notes'][0]['title'] if selected else snapshot['workspace']['title']
        try:
            notes=citation_result['citation_notes']
            if format_ not in {'docx','docxlive'}:markdown=template_markdown(markdown,template,title)
            def latex_document():
                protected,math=prepare_math(markdown)
                source=restore_math(_tex_bundle(protected,_png_figures(figures)),math)
                return apply_tex_template(tex_notes(source,notes,note_placement),template,title)
            if format_ == 'md':
                data = markdown_notes(markdown,notes).encode('utf-8')
            elif format_ == 'docxlive':
                data=render_live_docx(raw_markdown,snapshot['documents'],word_style=query.get('word_style','ieee'),image_resolver=lambda target:figures[target]['bytes'] if target in figures else None)
                data=apply_docx_template(data,template,title)
            elif format_ == 'docx':
                data = render_docx(markdown, image_resolver=lambda target: figures[target]['bytes'] if target in figures else None)
                data=apply_docx_notes(data,notes,note_placement)
                data=apply_docx_template(data,template,title)
            elif format_ == 'texpdf' or (format_=='pdf' and (notes or template['profile']!='none')):
                data=compile_tex(latex_document(),{figure['path']:figure['bytes'] for figure in _png_figures(figures).values()})
            elif format_ == 'pdf':
                data = _pdf(markdown, title, _png_figures(figures),template)
            elif format_ == 'tex':
                protected,math=prepare_math(markdown)
                text=apply_tex_template(tex_notes(restore_math(render_latex(protected),math),notes,note_placement),template,title)
                if figures:
                    text = '% Managed figures are caption placeholders in this source-only export. Use a TeX bundle to include image assets.\n' + text
                data = text.encode('utf-8')
            elif format_ == 'texzip':
                figures = _png_figures(figures)
                data = _zip([('main.tex', latex_document().encode('utf-8')), *[(figure['path'], figure['bytes']) for figure in figures.values()]])
            elif format_ == 'html':
                image_url = lambda target: 'data:' + figures[target]['mime'] + ';base64,' + base64.b64encode(figures[target]['bytes']).decode('ascii') if target in figures else None
                data = apply_html_template(html_notes(_html_document(markdown, title, image_url,template_css(template),language),notes),template,title).encode('utf-8')
            else:
                figures = _png_figures(figures)
                text = apply_html_template(html_notes(_html_document(markdown, title, lambda target: '/' + figures[target]['path'] if target in figures else None,template_css(template),language),notes),template,title)
                for figure in figures.values():
                    text = text.replace('src="/' + figure['path'] + '"', 'src="' + figure['path'] + '"')
                data = _zip([('index.html', text.encode('utf-8')), ('README.txt', _reading_readme(style)), *[(figure['path'], figure['bytes']) for figure in figures.values()]])
        except (ManuscriptError, ImportError, ValueError) as error:
            raise ExportError(str(error)) from error
    if len(data) > LIMIT:
        raise ExportError('Export exceeds the 47 MiB bound; no output was published.', 413)
    extension = 'zip' if format_ in {'texzip', 'share'} else 'json' if format_ == 'csljson' else 'pdf' if format_=='texpdf' else 'docx' if format_=='docxlive' else format_
    return data, MIME[format_], ('Kosh-draft.' if selected else 'Research-workspace.') + extension
