"""Bounded offline adapter to the vendored citeproc-js CSL processor.

Style rules, sorting, ambiguity resolution and collapse belong to citeproc-js.
This module translates reviewed metadata and its HTML output, never PDF pages.
"""
from __future__ import annotations

from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote
import xml.etree.ElementTree as ET


class CSLError(ValueError):
    pass


ROOT = Path(__file__).resolve().parent
STYLES = frozenset({'vancouver', 'apa', 'ieee', 'chicago-note'})
MAX_BYTES = 8_000_000
TYPE_MAP = {'journal_article': 'article-journal', 'book': 'book',
            'book_chapter': 'chapter', 'report': 'report', 'thesis': 'thesis', 'other': 'article'}
FIELD_MAP = {'title': 'title', 'journal': 'container-title', 'journal_abbreviation': 'container-title-short',
             'volume': 'volume', 'issue': 'issue', 'pages': 'page', 'publisher': 'publisher',
             'publisher_place': 'publisher-place', 'edition': 'edition', 'url': 'URL',
             'isbn': 'ISBN', 'issn': 'ISSN', 'report_number': 'number', 'thesis_type': 'genre'}


def _literal(value):
    # citeproc-js escapes ampersands itself, but interprets known HTML tags in
    # metadata. Shield angles with reversible private characters until its
    # output has been parsed. Doubling the escape character preserves literal
    # private characters too; no HTML entity is decoded twice.
    return str(value).replace('\ue000', '\ue000\ue000').replace('<', '\ue000\ue001').replace('>', '\ue000\ue002')


def _unshield(value):
    return re.sub('\ue000([\ue000\ue001\ue002])', lambda match: {'\ue000': '\ue000', '\ue001': '<', '\ue002': '>'}[match[1]], value)


def normalized_doi(value):
    value = re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)', '', str(value).strip(), flags=re.I)
    value = unquote(value)
    return value if re.fullmatch(r'10\.\d{4,9}/[^\s<>]+', value) else ''


def metadata_to_csl(identifier, metadata):
    """Map metadata only; extracted source-file page positions are not input."""
    result = {'id': identifier, 'type': TYPE_MAP.get(metadata.get('type'), 'article')}
    for source, target in FIELD_MAP.items():
        if source in {'journal', 'journal_abbreviation', 'issue'} and metadata.get('type') != 'journal_article':
            continue
        value = str(metadata.get(source, '') or '').strip()
        if value:
            result[target] = _literal(value)
    if metadata.get('type') == 'book_chapter':
        result['container-title'] = _literal(metadata.get('booktitle', '') or '')
    if metadata.get('type') == 'thesis' and metadata.get('institution'):
        result['publisher'] = _literal(metadata['institution'])
    raw_doi = str(metadata.get('doi', '') or '').strip()
    doi = normalized_doi(raw_doi)
    if doi:
        result['DOI'] = _literal(doi)
    for source, target, fallback in (('author_list', 'author', 'authors'), ('editor_list', 'editor', 'editors')):
        names = metadata.get(source) or ([{'literal': str(metadata[fallback])}] if metadata.get(fallback) else [])
        if names:
            result[target] = [{key: _literal(value) for key, value in name.items()
                               if key in {'family', 'given', 'literal', 'suffix', 'non-dropping-particle', 'dropping-particle'} and value}
                              for name in names]
    year = str(metadata.get('year', '') or '').strip()
    if year:
        result['issued'] = {'date-parts': [[int(year)]]} if re.fullmatch(r'\d{1,4}', year) else {'literal': _literal(year)}
    return result


def _node_binary():
    bundled = ROOT / 'tools' / 'node' / 'node.exe'
    if bundled.is_file():
        return bundled
    # Explicit development location; never resolve a document-supplied executable.
    development = Path(r'C:\Program Files\nodejs\node.exe')
    if development.is_file():
        return development
    raise CSLError('Local CSL runtime is missing. Repair the Kosh installation to restore bundled Node.js.')


def _style(style, style_xml):
    if style_xml is None:
        if style not in STYLES:
            raise CSLError('Choose an installed CSL citation style.')
        path = ROOT / 'vendor' / 'csl' / 'styles' / (style + '.csl')
        try:
            style_xml = path.read_text(encoding='utf-8-sig')
        except OSError as exc:
            raise CSLError('Installed CSL style is missing: ' + style + '.') from exc
    if not isinstance(style_xml, str) or len(style_xml.encode('utf-8')) > 1024 * 1024:
        raise CSLError('CSL style must be XML within 1 MiB.')
    if re.search(r'<!\s*(?:DOCTYPE|ENTITY)\b', style_xml, re.I):
        raise CSLError('CSL styles cannot contain document types or external entities.')
    try:
        tree = ET.fromstring(style_xml)
    except ET.ParseError as exc:
        raise CSLError('CSL style XML is invalid.') from exc
    ns = '{http://purl.org/net/xbiblio/csl}'
    if tree.tag != ns + 'style' or tree.find(ns + 'citation') is None:
        raise CSLError('Use an independent CSL style with citation rules; dependent styles need their parent.')
    return style_xml


class _Markdown(HTMLParser):
    """Allow only CSL's typography; metadata text always stays escaped literal."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.closings = [], []

    def handle_data(self, data):
        self.parts.append(re.sub(r'([\\*_`<>])', r'\\\1', _unshield(data)))

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        opening = closing = ''
        if tag in {'i', 'em'}:
            opening = closing = '*'
        elif tag in {'b', 'strong'}:
            opening = closing = '**'
        elif tag in {'sup', 'sub'}:
            opening, closing = '<' + tag + '>', '</' + tag + '>'
        elif tag == 'span':
            style = attributes.get('style', '')
            if re.search(r'vertical-align:\s*super', style):
                opening, closing = '<sup>', '</sup>'
            elif re.search(r'vertical-align:\s*sub', style):
                opening, closing = '<sub>', '</sub>'
            elif re.search(r'font-style:\s*italic', style):
                opening = closing = '*'
            elif re.search(r'font-weight:\s*bold', style):
                opening = closing = '**'
        elif tag == 'div' and 'csl-right-inline' in attributes.get('class', ''):
            self.parts.append(' ')
        elif tag == 'br':
            self.parts.append(' ')
            return
        self.parts.append(opening)
        self.closings.append((tag, closing))

    def handle_endtag(self, tag):
        if self.closings and self.closings[-1][0] == tag:
            self.parts.append(self.closings.pop()[1])


def _markdown(value):
    parser = _Markdown()
    parser.feed(value)
    parser.close()
    value = ''.join(parser.parts).strip()
    # CSL numeric brackets are literal. Escape only text that could become a
    # Markdown link/image from metadata, preserving citation punctuation.
    return re.sub(r'(?<!\\)\[([^\]]*)\](?=\(|\[)', r'\\[\1\\]', value)


def render(items, clusters, style='vancouver', *, style_xml=None, language=None, locales=None):
    if style_xml is None and style not in STYLES:
        raise CSLError('Choose an installed CSL citation style.')
    style_xml = _style(style, style_xml)
    tree = ET.fromstring(style_xml)
    style_class = tree.get('class', 'in-text')
    language = language or tree.get('default-locale') or 'en-US'
    from csl_styles import StyleError, describe_locale, select_language
    if locales is None:
        locales = {}
        for path in (ROOT / 'vendor/csl/locales').glob('locales-*.xml'):
            xml = path.read_text(encoding='utf-8-sig')
            locales[describe_locale(xml)] = xml
    try:
        if not isinstance(locales, dict) or any(describe_locale(xml) != key for key, xml in locales.items()):
            raise StyleError('Locale identity mismatch.')
        language = select_language(language, locales)
    except StyleError as exc:
        raise CSLError(str(exc)) from exc
    if language not in locales:
        raise CSLError('CSL locale unavailable: ' + str(language) + '; no English fallback was used.')
    # Bound IPC to the chosen language, its same-language variants and English
    # for explicit English terms. Do not transfer the entire cached inventory.
    primary = language.split('-')[0]
    locales = {key: xml for key, xml in locales.items() if key == 'en-US' or key.split('-')[0] == primary}
    if not clusters:
        return {'citations': [], 'references': [], 'bibliography_ids': [], 'item_numbers': {}, 'citation_format': '', 'style_class': style_class, 'language': language}
    citation_format = next((element.get('citation-format') for element in tree.iter()
                            if element.get('citation-format')), tree.get('class', 'in-text'))
    request = json.dumps({'items': items, 'clusters': clusters, 'style_xml': style_xml,
                          'citation_format': citation_format, 'language': language, 'locales': locales}, ensure_ascii=False).encode('utf-8')
    if len(request) > MAX_BYTES:
        raise CSLError('CSL request exceeds the 8,000,000 byte limit.')
    environment = {key: value for key, value in os.environ.items() if not key.upper().startswith('NODE_')}
    try:
        process = subprocess.run([str(_node_binary()), '--max-old-space-size=256', str(ROOT / 'scripts' / 'csl_render.js')],
                                 input=request, capture_output=True, timeout=15, cwd=str(ROOT), env=environment,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CSLError('Local CSL rendering failed or timed out; no limited formatter fallback was used.') from exc
    if process.returncode or len(process.stdout) > MAX_BYTES:
        raise CSLError('Local CSL processor rejected the citation request; verify the style and metadata.')
    try:
        result = json.loads(process.stdout)
        if len(result['citations']) != len(clusters) or any(not isinstance(value, str) for value in result['citations'] + result['references']):
            raise ValueError('Invalid processor response')
        result['citations'] = [_markdown(value) for value in result['citations']]
        result['references'] = [_markdown(value) for value in result['references']]
        return result
    except (ValueError, KeyError, TypeError) as exc:
        raise CSLError('Local CSL processor returned an invalid response.') from exc
