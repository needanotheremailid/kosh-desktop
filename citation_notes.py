"""Real Word note parts and format-specific CSL note placement."""
import copy
import html
import io
import zipfile
from lxml import etree as ET
from manuscript import inline_tokens, _latex_inline, render_html

W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R='http://schemas.openxmlformats.org/package/2006/relationships'
C='http://schemas.openxmlformats.org/package/2006/content-types'


def markdown_notes(text, notes):
    for note in notes: text=text.replace(note['token'],'[^'+str(note['number'])+']')
    return text+ ('\n\n'+'\n\n'.join('[^'+str(note['number'])+']: '+note['text'] for note in notes) if notes else '')


def html_notes(text, notes):
    for note in notes:
        number=str(note['number'])
        text=text.replace(note['token'],'<sup><a href="#citation-note-'+number+'">'+number+'</a></sup>')
    if notes:
        section='<section class="citation-notes"><h2>Citation notes</h2><ol>'
        section+=''.join('<li id="citation-note-'+str(note['number'])+'">'+render_html(note['text'])+'</li>' for note in notes)
        text=text.replace('</body>',section+'</ol></section></body>')
    return text


def tex_notes(text, notes, mode='footnote'):
    if mode not in {'footnote','endnote'}: raise ValueError('Choose footnote or endnote placement.')
    for note in notes:
        value=_latex_inline(inline_tokens(note['text']))
        replacement=(r'\footnote{'+value+'}') if mode=='footnote' else r'\textsuperscript{'+str(note['number'])+'}'
        text=text.replace(note['token'],replacement)
    if notes and mode=='endnote':
        section=r'\section*{Citation notes}'+'\n'+r'\begin{enumerate}'+'\n'
        section+='\n'.join(r'\item '+_latex_inline(inline_tokens(note['text'])) for note in notes)+'\n'+r'\end{enumerate}'+'\n'
        text=text.replace(r'\end{document}',section+r'\end{document}')
    return text


def apply_docx_notes(data, notes, mode='footnote'):
    if not notes: return data
    if mode not in {'footnote','endnote'}: raise ValueError('Choose footnote or endnote placement.')
    with zipfile.ZipFile(io.BytesIO(data)) as archive: parts={name:archive.read(name) for name in archive.namelist()}
    document=ET.fromstring(parts['word/document.xml'])
    root=ET.Element('{'+W+'}'+mode+'s',nsmap={'w':W})
    def node(name,**attrs):
        element=ET.Element('{'+W+'}'+name)
        for key,value in attrs.items():element.set('{'+W+'}'+key,str(value))
        return element
    for section in document.iter('{'+W+'}sectPr'):
        properties=section.find('{'+W+'}'+mode+'Pr')
        if properties is None:
            properties=node(mode+'Pr');section.insert(0,properties)
        for existing in list(properties):
            if existing.tag=='{'+W+'}numFmt':properties.remove(existing)
        properties.append(node('numFmt',val='decimal'))
    for number, kind in [(-1,'separator'),(0,'continuationSeparator')]:
        note=node(mode,id=number,type=kind);p=node('p');r=node('r');r.append(node(kind));p.append(r);note.append(p);root.append(note)
    def append_tokens(parent,tokens,bold=False,italic=False):
        for token in tokens:
            kind=token['type']
            if kind in {'strong','emphasis'}:
                append_tokens(parent,token['children'],bold or kind=='strong',italic or kind=='emphasis');continue
            if 'children' in token:
                append_tokens(parent,token['children'],bold,italic);continue
            run=node('r');properties=node('rPr')
            if bold:properties.append(node('b'))
            if italic:properties.append(node('i'))
            if len(properties):run.append(properties)
            text=node('t');text.set('{http://www.w3.org/XML/1998/namespace}space','preserve');text.text=token.get('text','')
            run.append(text);parent.append(run)
    for item in notes:
        found=False
        for text in list(document.iter('{'+W+'}t')):
            if item['token'] not in (text.text or ''):continue
            run=text.getparent()
            if run.tag!='{'+W+'}r':raise ValueError('Citation note cannot be placed in this document structure.')
            before,after=text.text.split(item['token'],1)
            if before:
                prefix=copy.deepcopy(run);prefix.find('{'+W+'}t').text=before;run.addprevious(prefix)
            marker=node('r');properties=node('rPr');properties.append(node('vertAlign',val='superscript'));marker.append(properties)
            marker.append(node(mode+'Reference',id=item['number']));run.addprevious(marker)
            if after:
                suffix=copy.deepcopy(run);suffix.find('{'+W+'}t').text=after;run.addprevious(suffix)
            run.getparent().remove(run);found=True
        if not found:raise ValueError('Citation note marker was lost during Word export.')
        note=node(mode,id=item['number']);paragraph=node('p');marker=node('r');marker.append(node(mode+'Ref'));paragraph.append(marker)
        append_tokens(paragraph,inline_tokens(' '+item['text']));note.append(paragraph);root.append(note)
    path='word/'+mode+'s.xml'
    relationships=ET.fromstring(parts['word/_rels/document.xml.rels'])
    relationship=ET.SubElement(relationships,'{'+R+'}Relationship')
    ids={element.get('Id') for element in relationships}
    identifier='rIdKosh'+mode
    while identifier in ids:identifier+='X'
    relationship.attrib.update({'Id':identifier,'Type':'http://schemas.openxmlformats.org/officeDocument/2006/relationships/'+mode+'s','Target':mode+'s.xml'})
    types=ET.fromstring(parts['[Content_Types].xml'])
    ET.SubElement(types,'{'+C+'}Override',PartName='/'+path,ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.'+mode+'s+xml')
    for name,value in [('word/document.xml',document),(path,root),('word/_rels/document.xml.rels',relationships),('[Content_Types].xml',types)]:parts[name]=ET.tostring(value,xml_declaration=True,encoding='UTF-8',standalone=True)
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,value in parts.items():archive.writestr(name,value)
    return output.getvalue()
