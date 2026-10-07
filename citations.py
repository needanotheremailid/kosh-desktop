"""CSL manuscript citations over immutable Kosh source markers.

Publication formatting uses the offline citeproc-js processor. Source-file
locators remain a separate audit product; never infer publication pagination.
Entered/imported bibliographic claims still require review.
"""
from __future__ import annotations

import re

from csl_engine import CSLError, STYLES, metadata_to_csl, normalized_doi, render


class CitationError(ValueError):
    pass


ID = re.compile(r'^[a-f0-9]{32}$')
MARKER = re.compile(r'\[\[source:([a-f0-9]{32}):(\d{1,6})\]\]')
REFERENCE_MARKER = re.compile(r'\[\[reference:([a-f0-9]{32})\]\]')
ANY_MARKER = re.compile(r'\[\[(?:source|reference):([^\]\r\n]*)(?:\]\]|(?=\r?\n|$))')
FIGURE_KINDS = {'png', 'jpg', 'jpeg', 'webp'}
TYPES = {'journal_article', 'book', 'book_chapter', 'report', 'thesis', 'other'}


def citation_key(document_id):
    if not isinstance(document_id, str) or not ID.fullmatch(document_id):
        raise CitationError('Citation keys require the complete source identifier.')
    return 'Kosh' + document_id


def _value(metadata, key):
    return str(metadata.get(key, '') or '').strip()


def _authors(metadata):
    if metadata.get('author_list'):
        return metadata['author_list']
    if _value(metadata, 'authors'):
        return [{'literal': _value(metadata, 'authors')}]
    return []


def format_reference(metadata, style='vancouver', number=1, year_suffix='', *, style_xml=None):
    """Single-reference convenience API; manuscript numbering needs shared context."""
    if number != 1 or year_suffix:
        raise CitationError('CSL numbering and year suffixes require render_citations manuscript context.')
    try:
        result = render([metadata_to_csl('reference', metadata)], [['reference']], style, style_xml=style_xml)
        if not result['references']:
            raise CitationError('The selected CSL style has no bibliography.')
        return result['references'][0]
    except CSLError as exc:
        raise CitationError(str(exc)) from exc


def _reference_warnings(document, style):
    metadata, warnings = document['metadata'], []
    required = ['title', 'year']
    kind = _value(metadata, 'type')
    if not _authors(metadata):
        warnings.append('Author metadata missing.')
    if not metadata.get('author_list') and _value(metadata, 'authors'):
        warnings.append('Unstructured author text retained literally; verify names.')
    if kind == 'journal_article':
        required.extend(['journal', 'volume', 'pages'])
        if style == 'vancouver' and not _value(metadata, 'journal_abbreviation'):
            warnings.append('Entered journal name retained; abbreviation needs review.')
    elif kind in {'book', 'book_chapter', 'report'}:
        required.append('publisher')
        if style != 'apa':
            required.append('publisher_place')
        if kind == 'book_chapter':
            required.extend(['booktitle', 'editors', 'pages'])
    elif kind == 'thesis':
        if not (_value(metadata, 'institution') or _value(metadata, 'publisher')):
            warnings.append('Thesis institution missing.')
        if style != 'apa':
            required.append('publisher_place')
    else:
        warnings.append('Publication type is other/unsupported; reference needs review.')
    missing = [field for field in required if not _value(metadata, field) and not (field == 'journal' and _value(metadata, 'journal_abbreviation'))]
    if missing:
        warnings.append('Missing bibliographic fields: ' + ', '.join(missing) + '.')
    if _value(metadata, 'doi') and not normalized_doi(_value(metadata, 'doi')):
        entered = re.sub(r'([\\*_\[\]`<>])', r'\\\1', _value(metadata, 'doi'))
        warnings.append('DOI format needs review; entered value retained. Entered DOI: ' + entered + '.')
    if _value(metadata, 'catalogue_source'):
        warnings.append('Catalogue metadata only; citation does not verify the publication or claim.')
    if _value(metadata, 'provenance'):
        warnings.append(_value(metadata, 'provenance'))
    return [document['id'] + ': ' + warning for warning in warnings]


def _page_limit(document):
    for key in ('pages', 'page_count', 'text_pages'):
        value = document.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, (list, dict)):
            return len(value)
    return None


def render_citations(texts, documents, style='vancouver', locator='none', *, style_xml=None, language=None, locales=None, note_mode=False):
    if style_xml is None and style not in STYLES:
        raise CitationError('Choose an installed CSL citation style.')
    if locator not in {'none', 'internal'}:
        raise CitationError('Choose none or internal source-file locators.')
    if not isinstance(texts, list) or any(not isinstance(text, str) for text in texts) or sum(map(len, texts)) > 2_000_000:
        raise CitationError('Citation input must be a list of texts within 2,000,000 characters.')
    by_id = {document['id']: document for document in documents}
    warnings, canonical, canonical_docs, cited_ids, matches_by_text = [], {}, [], [], []
    publication_keys, seen_locators, evidence = {}, set(), []
    document_references, seen_documents = [], set()
    numbers = {}
    for text in texts:
        values = []
        for match in ANY_MARKER.finditer(text):
            source_marker = MARKER.fullmatch(match[0])
            reference_marker = REFERENCE_MARKER.fullmatch(match[0])
            valid = source_marker or reference_marker
            document = by_id.get(valid[1]) if valid else None
            page = int(source_marker[2]) if source_marker else None
            error_label = 'Unresolved document reference' if match[0].startswith('[[reference:') else 'Unresolved source reference'
            limit = _page_limit(document) if document and source_marker else None
            invalid_page = source_marker and (page < 1 or limit is not None and page > limit)
            figure = document and document.get('kind') in FIGURE_KINDS
            if not document or invalid_page or figure:
                warnings.append(error_label + ': ' + match[1] + '.' + (' Managed figure is not a bibliographic source or extracted evidence location.' if figure else ''))
                values.append({'match': match, 'valid': False})
                continue
            document_id = document['id']
            if source_marker and limit is None:
                warnings.append(document_id + ': Source-page bounds unavailable; parent must verify the location.')
            if document_id not in canonical:
                doi = normalized_doi(_value(document['metadata'], 'doi')).casefold()
                key = ('doi', doi) if doi else ('id', document_id)
                canonical_id = publication_keys.get(key)
                if canonical_id is None:
                    canonical_id = document_id
                    publication_keys[key] = document_id
                    canonical_docs.append(document)
                    numbers[document_id] = len(canonical_docs)
                else:
                    previous = by_id[canonical_id]['metadata']
                    for field in ('title', 'year', 'journal', 'publisher'):
                        if _value(previous, field).casefold() != _value(document['metadata'], field).casefold():
                            warnings.append(document_id + ': Same DOI has conflicting ' + field + '; first cited record retained for bibliography.')
                canonical[document_id] = canonical_id
                cited_ids.append(document_id)
            canonical_id = canonical[document_id]
            values.append({'match': match, 'valid': True, 'document': document, 'canonical_id': canonical_id, 'page': page})
            if reference_marker:
                if document_id not in seen_documents:
                    seen_documents.add(document_id)
                    document_references.append({'marker': match[0], 'document_id': document_id,
                                                'label': str(numbers[canonical_id]), 'kind': document.get('kind', '')})
                    warnings.append(document_id + ': Document-level reference; no source location supplied.')
                continue
            locator_key = document_id, page
            if locator_key not in seen_locators:
                seen_locators.add(locator_key)
                evidence.append({'marker': match[0], 'document_id': document_id, 'page': page,
                                 'label': str(numbers[canonical_id]), 'kind': document.get('kind', '')})
        matches_by_text.append(values)
    # Build all clusters before processing so later citations can revise earlier
    # disambiguation. A cluster is adjacent markers across at most one newline.
    plans, clusters = [], []
    for text, matches in zip(texts, matches_by_text):
        parts, position, index = [], 0, 0
        while index < len(matches):
            value = matches[index]
            match = value['match']
            parts.append(text[position:match.start()])
            if not value['valid']:
                label = 'Unresolved document reference' if match[0].startswith('[[reference:') else 'Unresolved source reference'
                parts.append('[' + label + ': ' + match[1] + ']')
                position, index = match.end(), index + 1
                continue
            group = [value]
            end = match.end()
            index += 1
            while index < len(matches) and matches[index]['valid'] and re.fullmatch(r'[ \t]*(?:,[ \t]*)?(?:\r?\n[ \t]*)?', text[end:matches[index]['match'].start()]):
                group.append(matches[index])
                end = matches[index]['match'].end()
                index += 1
            parts.append((len(clusters), group))
            clusters.append(list(dict.fromkeys(value['canonical_id'] for value in group)))
            position = end
        parts.append(text[position:])
        plans.append(parts)
    try:
        result = render([metadata_to_csl(document['id'], document['metadata']) for document in canonical_docs],
                        clusters, style, style_xml=style_xml, language=language, locales=locales)
    except CSLError as exc:
        raise CitationError(str(exc)) from exc
    # Some numeric journal styles number in bibliography-sort order. Audit
    # labels must follow the processor's numbering rather than a guessed order.
    for location in evidence + document_references:
        location['label'] = str(result['item_numbers'][canonical[location['document_id']]])
    rendered, citation_notes = [], []
    if note_mode and result.get('style_class') == 'note':
        for index, value in enumerate(result['citations']):
            token = 'KOSHNOTEREF' + str(index+1) + 'TOKEN'
            while any(token in text for text in texts): token += 'X'
            citation_notes.append({'number':index+1,'token':token,'text':value})
    for parts in plans:
        output = []
        for part in parts:
            if isinstance(part, str):
                output.append(part)
                continue
            cluster_index, group = part
            output.append(citation_notes[cluster_index]['token'] if citation_notes else result['citations'][cluster_index])
            if locator == 'internal':
                locations, seen = [], set()
                for value in group:
                    document, page = value['document'], value['page']
                    key = document['id'], page
                    if key not in seen:
                        seen.add(key)
                        locations.append('document reference; no source location' if page is None else
                                         ('PDF p. ' if document.get('kind') == 'pdf' else 'text unit ') + str(page))
                output.append(' [source files: ' + '; '.join(locations) + ']')
        rendered.append(''.join(output))
    for document in canonical_docs:
        warnings.extend(_reference_warnings(document, style))
    return {'texts': rendered, 'references': result['references'], 'warnings': list(dict.fromkeys(warnings)),
            'evidence_locators': evidence, 'document_references': document_references, 'cited_ids': cited_ids,
            'citation_format': result['citation_format'], 'style_class':result.get('style_class','in-text'), 'citation_notes':citation_notes}
