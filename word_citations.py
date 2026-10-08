"""Document-local Word citation fields; no COM, macros or global source edits.

Word uses its installed XSL styles, not CSL. Unrefreshed field results carry the
static CSL (Vancouver) rendering so the file reads correctly before any refresh;
Word's Update Field regenerates them from the embedded current source list.
"""
from __future__ import annotations

import io
import re
import uuid
import zipfile
from lxml import etree as ET

from citations import ANY_MARKER, MARKER, REFERENCE_MARKER, citation_key, normalized_doi, _page_limit, render_citations
from manuscript import render_docx

B = 'http://schemas.openxmlformats.org/officeDocument/2006/bibliography'
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
REL = 'http://schemas.openxmlformats.org/package/2006/relationships'
WORD_STYLES = {
    'ieee': ('IEEE2006OfficeOnline.xsl', 'IEEE'),
    'apa6': ('APASixthEditionOfficeOnline.xsl', 'APA Sixth Edition'),
    'iso690-numeric': ('ISO690Nmerical.XSL', 'ISO 690 - Numerical Reference'),
}


class WordCitationError(ValueError):
    pass


def _child(parent, name, value=None):
    node = ET.SubElement(parent, '{'+B+'}'+name)
    if value is not None:
        node.text = str(value)
    return node


def _source(parent, document):
    metadata = document['metadata']
    node = _child(parent, 'Source')
    _child(node, 'Tag', citation_key(document['id']))
    types = {'journal_article': 'JournalArticle', 'book': 'Book', 'book_chapter': 'BookSection',
             'report': 'Report', 'thesis': 'Report', 'other': 'Misc'}
    _child(node, 'SourceType', types.get(metadata.get('type'), 'Misc'))
    _child(node, 'Guid', '{'+str(uuid.UUID(document['id'])).upper()+'}')
    _child(node, 'LCID', '1033')
    authors = metadata.get('author_list') or ([{'literal': metadata['authors']}] if metadata.get('authors') else [])
    if authors:
        author = _child(_child(node, 'Author'), 'Author')
        if any(person.get('literal') for person in authors):
            # Word cannot mix corporate and person authors in one author role.
            _child(author, 'Corporate', '; '.join(person.get('literal') or ' '.join(filter(None, [person.get('given'), person.get('family')])) for person in authors))
        else:
            names = _child(author, 'NameList')
            for person in authors:
                entry = _child(names, 'Person')
                _child(entry, 'Last', person.get('family', ''))
                _child(entry, 'First', person.get('given', ''))
    fields = {'title': 'Title', 'year': 'Year', 'journal': 'JournalName', 'volume': 'Volume',
              'issue': 'Issue', 'pages': 'Pages', 'publisher': 'Publisher', 'publisher_place': 'City',
              'booktitle': 'BookTitle', 'edition': 'Edition', 'url': 'URL', 'doi': 'DOI',
              'isbn': 'StandardNumber', 'report_number': 'ReportNumber', 'institution': 'Institution'}
    for key, field in fields.items():
        if metadata.get(key):
            _child(node, field, metadata[key])


def _plain(value):
    # csl_engine emits a small Markdown dialect (escapes, *emphasis*, <sup>/<sub>).
    # ponytail: cached preview is plain text; Word restores typography on refresh.
    return re.sub(r'\\(.)|</?su[pb]>|\*+', lambda match: match[1] or '', value)


def _field(code, result):
    def run(child):
        node = ET.Element('{'+W+'}r')
        node.append(child)
        return node
    begin = ET.Element('{'+W+'}fldChar', {'{'+W+'}fldCharType': 'begin', '{'+W+'}dirty': 'true'})
    instruction = ET.Element('{'+W+'}instrText', {'{http://www.w3.org/XML/1998/namespace}space': 'preserve'})
    instruction.text = code
    separate = ET.Element('{'+W+'}fldChar', {'{'+W+'}fldCharType': 'separate'})
    end = ET.Element('{'+W+'}fldChar', {'{'+W+'}fldCharType': 'end'})
    shown = ET.Element('{'+W+'}r')
    for index, line in enumerate([result] if isinstance(result, str) else result):
        if index:
            ET.SubElement(shown, '{'+W+'}br')
        ET.SubElement(shown, '{'+W+'}t', {'{http://www.w3.org/XML/1998/namespace}space': 'preserve'}).text = line
    return [run(begin), run(instruction), run(separate), shown, run(end)]


def render_live_docx(markdown, documents, *, word_style='ieee', image_resolver=None):
    if word_style not in WORD_STYLES:
        raise WordCitationError('Choose a native Word style: IEEE, APA sixth edition or ISO 690 numerical. CSL/Vancouver styles are not native Word styles.')
    by_id = {item['id']: item for item in documents}
    cited, publication = {}, {}
    plans, markers = [], []
    prefix = 'KOSHLIVE'+uuid.uuid4().hex.upper()
    def replace(match):
        marker = MARKER.fullmatch(match[0]) or REFERENCE_MARKER.fullmatch(match[0])
        source = by_id.get(marker[1]) if marker else None
        page = int(marker[2]) if marker and match[0].startswith('[[source:') else None
        limit = _page_limit(source) if source else None
        if not source or source.get('kind') in {'png', 'jpg', 'jpeg', 'webp'} or page is not None and (page < 1 or limit is not None and page > limit):
            raise WordCitationError('Unresolved source marker cannot become a native Word citation.')
        identifier = source['id']
        doi = normalized_doi(str(source['metadata'].get('doi', ''))).casefold()
        identity = ('doi', doi) if doi else ('id', identifier)
        canonical = publication.setdefault(identity, identifier)
        cited.setdefault(canonical, by_id[canonical])
        sentinel = prefix+str(len(plans))+'END'
        plans.append((sentinel, ' CITATION '+citation_key(canonical)+' \\l 1033 ', '[Update citation in Word]'))
        markers.append(match[0])
        return sentinel
    marked = ANY_MARKER.sub(replace, markdown)
    # Cached field results: one CSL rendering per marker (each its own field,
    # never merged), so the file reads correctly before Word refreshes fields.
    try:
        preview = render_citations(markers, documents) if markers else None
    except Exception:  # ponytail: preview is cosmetic; any failure keeps the placeholders
        preview = None
    if preview:
        plans = [(sentinel, code, _plain(text) or placeholder) for (sentinel, code, placeholder), text in zip(plans, preview['texts'])]
    if cited:
        sentinel = prefix+str(len(plans))+'END'
        plans.append((sentinel, ' BIBLIOGRAPHY \\l 1033 ', [_plain(line) for line in (preview or {}).get('references', [])] or 'Update bibliography in Word.'))
        marked += '\n\n## References\n\n'+sentinel+'\n'
    original = render_docx(marked, image_resolver=image_resolver)
    with zipfile.ZipFile(io.BytesIO(original)) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    root = ET.fromstring(parts['word/document.xml'])
    mapping = {sentinel: (code, result) for sentinel, code, result in plans}
    pattern = re.compile('('+ '|'.join(map(re.escape, mapping))+')') if mapping else None
    for paragraph in root.iter('{'+W+'}p'):
        for run in list(paragraph):
            if run.tag != '{'+W+'}r':
                continue
            text = run.find('{'+W+'}t')
            if text is None or pattern is None or not pattern.search(text.text or ''):
                continue
            insertion = list(paragraph).index(run)
            paragraph.remove(run)
            for piece in pattern.split(text.text or ''):
                if not piece:
                    continue
                if piece in mapping:
                    code, result = mapping[piece]
                    replacements = _field(code, result)
                    if code.strip().startswith('BIBLIOGRAPHY '):
                        # Word replaces the field result with a bibliography
                        # table. Keep its nonprinting end outside that result,
                        # with a small paragraph mark, so refresh cannot leave a
                        # normal-sized empty closing paragraph on a new page.
                        closing = ET.Element('{'+W+'}p')
                        properties = ET.SubElement(closing, '{'+W+'}pPr')
                        ET.SubElement(properties, '{'+W+'}spacing', {'{'+W+'}before':'0', '{'+W+'}after':'0'})
                        mark = ET.SubElement(properties, '{'+W+'}rPr')
                        for name in ('sz', 'szCs'):
                            ET.SubElement(mark, '{'+W+'}'+name, {'{'+W+'}val':'2'})
                        closing.append(replacements.pop())
                        paragraph.addnext(closing)
                else:
                    replacement = ET.Element('{'+W+'}r')
                    properties = run.find('{'+W+'}rPr')
                    if properties is not None:
                        replacement.append(ET.fromstring(ET.tostring(properties)))
                    value = ET.SubElement(replacement, '{'+W+'}t', {'{http://www.w3.org/XML/1998/namespace}space':'preserve'})
                    value.text = piece
                    replacements = [replacement]
                for replacement in replacements:
                    paragraph.insert(insertion, replacement); insertion += 1
    parts['word/document.xml'] = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    filename, name = WORD_STYLES[word_style]
    sources = ET.Element('{'+B+'}Sources', {'SelectedStyle': '\\'+filename, 'StyleName': name, 'Version': '6'})
    for source in cited.values():
        _source(sources, source)
    parts['customXml/item1.xml'] = ET.tostring(sources, encoding='utf-8', xml_declaration=True)
    properties_ns = 'http://schemas.openxmlformats.org/officeDocument/2006/customXml'
    props = ET.Element('{'+properties_ns+'}datastoreItem', {'{'+properties_ns+'}itemID': '{'+str(uuid.uuid4()).upper()+'}'})
    schema = ET.SubElement(props, '{'+properties_ns+'}schemaRefs')
    ET.SubElement(schema, '{'+properties_ns+'}schemaRef', {'{'+properties_ns+'}uri': B})
    parts['customXml/itemProps1.xml'] = ET.tostring(props, encoding='utf-8', xml_declaration=True)
    custom_rel = ET.Element('{'+REL+'}Relationships')
    ET.SubElement(custom_rel, '{'+REL+'}Relationship', {'Id':'rId1', 'Type':'http://schemas.openxmlformats.org/officeDocument/2006/relationships/customXmlProps', 'Target':'itemProps1.xml'})
    parts['customXml/_rels/item1.xml.rels'] = ET.tostring(custom_rel, encoding='utf-8', xml_declaration=True)
    relations = ET.fromstring(parts['word/_rels/document.xml.rels'])
    for relation in list(relations):
        if relation.attrib.get('Target') == '../customXml/item1.xml':
            relations.remove(relation)
    existing = {node.attrib['Id'] for node in relations}
    index = 1
    while 'rId'+str(index) in existing:
        index += 1
    ET.SubElement(relations, '{'+REL+'}Relationship', {'Id':'rId'+str(index), 'Type':'http://schemas.openxmlformats.org/officeDocument/2006/relationships/customXml', 'Target':'../customXml/item1.xml'})
    parts['word/_rels/document.xml.rels'] = ET.tostring(relations, encoding='utf-8', xml_declaration=True)
    content = ET.fromstring(parts['[Content_Types].xml'])
    if not any(node.attrib.get('PartName') == '/customXml/itemProps1.xml' for node in content):
        ET.SubElement(content, '{http://schemas.openxmlformats.org/package/2006/content-types}Override', {'PartName':'/customXml/itemProps1.xml', 'ContentType':'application/vnd.openxmlformats-officedocument.customXmlProperties+xml'})
    parts['[Content_Types].xml'] = ET.tostring(content, encoding='utf-8', xml_declaration=True)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path, data in parts.items():
            archive.writestr(path, data)
    return buffer.getvalue()
