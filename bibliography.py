"""Original bounded BibTeX/RIS metadata parser and interoperable serializers.

No document/network access, macro execution or inference of missing facts. Names
without explicit comma delimiters are literal names, not guessed family names.
This is a metadata subset, not a CSL style engine or full BibTeX implementation.
"""
from __future__ import annotations

import json
import re


class BibliographyError(ValueError):
    pass


MAX_TEXT = 2_000_000
MAX_RECORDS = 1000
BIB_TYPES = {'article': 'journal_article', 'book': 'book', 'inbook': 'book_chapter',
             'incollection': 'book_chapter', 'techreport': 'report',
             'phdthesis': 'thesis', 'mastersthesis': 'thesis', 'thesis': 'thesis'}
RIS_TYPES = {'JOUR': 'journal_article', 'BOOK': 'book', 'CHAP': 'book_chapter',
             'RPRT': 'report', 'THES': 'thesis', 'GEN': 'other'}
BIB_FIELDS = {'title': 'title', 'year': 'year', 'doi': 'doi', 'url': 'url',
              'journal': 'journal', 'shortjournal': 'journal_abbreviation',
              'volume': 'volume', 'number': 'issue', 'pages': 'pages',
              'publisher': 'publisher', 'address': 'publisher_place',
              'booktitle': 'booktitle', 'edition': 'edition', 'isbn': 'isbn',
              'issn': 'issn', 'abstract': 'abstract', 'note': 'note',
              'institution': 'institution', 'school': 'institution', 'type': 'thesis_type'}
RIS_FIELDS = {'TI': 'title', 'T1': 'title', 'PY': 'year', 'Y1': 'year', 'DO': 'doi',
              'UR': 'url', 'JO': 'journal', 'JF': 'journal', 'T2': 'journal',
              'JA': 'journal_abbreviation', 'J2': 'journal_abbreviation',
              'VL': 'volume', 'IS': 'issue', 'PB': 'publisher',
              'CY': 'publisher_place', 'ET': 'edition', 'AB': 'abstract',
              'N1': 'note', 'ID': 'id'}


def _record(identifier='', kind='other'):
    return {'id': identifier, 'title': '', 'authors': '', 'author_list': [],
            'type': kind, 'year': ''}


def _plain(value):
    """Remove grouping braces, retaining escaped literal punctuation/commands."""
    result = []
    index = 0
    while index < len(value):
        char = value[index]
        if char == '\\' and index + 1 < len(value):
            following = value[index + 1]
            if following in '{}%&#_$"\\':
                result.append(following)
                index += 2
                continue
            # Unsupported TeX accent/format macros remain visible for review.
            result.append(char)
        elif char not in '{}':
            result.append(char)
        index += 1
    return re.sub(r'\s+', ' ', ''.join(result)).strip()


def _split_authors(value):
    start, depth, index = 0, 0, 0
    names = []
    while index < len(value):
        if value[index] == '\\':
            index += 2
            continue
        if value[index] == '{':
            depth += 1
        elif value[index] == '}':
            depth -= 1
        elif depth == 0:
            delimiter = re.match(r'\s+and\s+', value[index:], re.I)
            if delimiter:
                names.append(value[start:index].strip())
                index += len(delimiter[0])
                start = index
                continue
        index += 1
    if value[start:].strip():
        names.append(value[start:].strip())
    return names


def _name(value):
    if value.startswith('{') and value.endswith('}'):
        return {'literal': _plain(value)}
    components = value.split(',')
    if len(components) == 2 and components[0].strip():
        return {'family': _plain(components[0]), 'given': _plain(components[1])}
    return {'literal': _plain(value)}


def _set_authors(record, names):
    record['author_list'] = [_name(name) for name in names if _plain(name)]
    record['authors'] = '; '.join(name.get('literal') or
                                 (name['family'] + (', ' + name['given'] if name['given'] else ''))
                                 for name in record['author_list'])


class _BibReader:
    def __init__(self, text):
        self.text, self.pos, self.warnings = text, 0, []
        self.record_warnings = []

    def space(self):
        while self.pos < len(self.text):
            if self.text[self.pos].isspace():
                self.pos += 1
            elif self.text[self.pos] == '%':
                end = self.text.find('\n', self.pos)
                self.pos = len(self.text) if end < 0 else end + 1
            else:
                break

    def balanced(self, closing):
        """Read one brace or quote value with nested brace protection."""
        start, depth = self.pos, 0
        while self.pos < len(self.text):
            char = self.text[self.pos]
            if char == '\\':
                self.pos += 2
                continue
            if char == closing and depth == 0:
                value = self.text[start:self.pos]
                self.pos += 1
                return value
            if char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
                if depth < 0:
                    raise BibliographyError('Unbalanced brace in BibTeX value.')
            self.pos += 1
        raise BibliographyError('Unclosed BibTeX value or entry.')

    def value(self, closing, label):
        pieces, supported = [], True
        while True:
            self.space()
            if self.pos >= len(self.text):
                raise BibliographyError('Missing BibTeX field value.')
            char = self.text[self.pos]
            if char in '{"':
                self.pos += 1
                pieces.append(self.balanced('}' if char == '{' else '"'))
            else:
                start = self.pos
                while self.pos < len(self.text) and self.text[self.pos] not in ',#' + closing and not self.text[self.pos].isspace():
                    self.pos += 1
                value = self.text[start:self.pos]
                if not value:
                    raise BibliographyError('Missing BibTeX field value.')
                if re.fullmatch(r'\d+', value):
                    pieces.append(value)
                else:
                    supported = False
                    self.warnings.append(f'{label}: unsupported macro {value!r}; field omitted.')
            self.space()
            if self.pos < len(self.text) and self.text[self.pos] == '#':
                self.pos += 1
            else:
                return ''.join(pieces) if supported else None

    def parse(self):
        records, identifiers = [], set()
        while True:
            self.space()
            if self.pos == len(self.text):
                return records
            if self.text[self.pos] != '@':
                raise BibliographyError('Expected a BibTeX @entry; outside-entry text is unsupported.')
            self.pos += 1
            match = re.match(r'[A-Za-z]+', self.text[self.pos:])
            if not match:
                raise BibliographyError('Missing BibTeX entry type.')
            entry_type = match[0].lower()
            self.pos += len(match[0])
            self.space()
            if self.pos >= len(self.text) or self.text[self.pos] not in '{(':
                raise BibliographyError('Expected a brace or parenthesis after BibTeX type.')
            closing = '}' if self.text[self.pos] == '{' else ')'
            self.pos += 1
            if entry_type in {'comment', 'preamble', 'string'}:
                self.balanced(closing)
                if entry_type != 'comment':
                    self.warnings.append(f'@{entry_type}: unsupported macro/preamble content was not evaluated.')
                continue
            start = self.pos
            while self.pos < len(self.text) and self.text[self.pos] not in ',' + closing:
                self.pos += 1
            identifier = self.text[start:self.pos].strip()
            if not identifier or self.pos >= len(self.text):
                raise BibliographyError('Missing BibTeX identifier or unclosed entry.')
            if identifier in identifiers:
                raise BibliographyError(f'Duplicate BibTeX record identifier {identifier!r}.')
            identifiers.add(identifier)
            warning_start = len(self.warnings)
            fields = {}
            if self.text[self.pos] == ',':
                self.pos += 1
            while True:
                self.space()
                if self.pos >= len(self.text):
                    raise BibliographyError('Unclosed BibTeX entry.')
                if self.text[self.pos] == closing:
                    self.pos += 1
                    break
                match = re.match(r'[A-Za-z][A-Za-z0-9_-]*', self.text[self.pos:])
                if not match:
                    raise BibliographyError('Invalid BibTeX field name.')
                key = match[0].lower()
                self.pos += len(match[0])
                self.space()
                if self.pos >= len(self.text) or self.text[self.pos] != '=':
                    raise BibliographyError('Expected = after a BibTeX field name.')
                self.pos += 1
                value = self.value(closing, identifier + '/' + key)
                if key in fields:
                    self.warnings.append(f'{identifier}: duplicate {key} field; first value retained.')
                else:
                    fields[key] = value
                if self.pos < len(self.text) and self.text[self.pos] == ',':
                    self.pos += 1
                elif self.pos >= len(self.text) or self.text[self.pos] != closing:
                    raise BibliographyError('Expected a comma or closing delimiter after BibTeX value.')
            record = _record(identifier, BIB_TYPES.get(entry_type, 'other'))
            for key, destination in BIB_FIELDS.items():
                if fields.get(key) is not None and key in fields:
                    destination = 'report_number' if key == 'number' and record['type'] == 'report' else destination
                    if record.get(destination):
                        self.warnings.append(f'{identifier}: duplicate {destination} alias; first value retained.')
                    else:
                        record[destination] = _plain(fields[key])
            if fields.get('author'):
                _set_authors(record, _split_authors(fields['author']))
            if fields.get('editor'):
                record['editors'] = '; '.join(_plain(name) for name in _split_authors(fields['editor']) if _plain(name))
            if any('\\' in value for value in fields.values() if isinstance(value, str)):
                self.warnings.append(f'{identifier}: escaped TeX text was retained where not supported; review metadata.')
            unsupported = sorted(set(fields) - set(BIB_FIELDS) - {'author', 'editor'})
            if unsupported:
                self.warnings.append(f'{identifier}: unsupported fields omitted: ' + ', '.join(unsupported) + '.')
            records.append(record)
            self.record_warnings.append(self.warnings[warning_start:])
            if len(records) > MAX_RECORDS:
                raise BibliographyError(f'Bibliographies support at most {MAX_RECORDS} records.')


def _parse_ris(text):
    records, warnings, current, previous = [], [], None, None
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        match = re.match(r'^([A-Z0-9]{2})\s{2}-\s?(.*)$', line)
        if not match:
            if current is not None and previous and line[:1].isspace():
                current[-1][1] += ' ' + line.strip()
                continue
            raise BibliographyError(f'Invalid RIS line {number}; expected TAG  - value.')
        tag, value = match.groups()
        value = value.strip()
        if tag == 'TY':
            if current is not None:
                raise BibliographyError('RIS record is missing its ER terminator.')
            current, previous = [[tag, value]], tag
            continue
        if current is None:
            raise BibliographyError(f'RIS line {number} occurs outside a TY/ER record.')
        if tag != 'ER':
            current.append([tag, value])
            previous = tag
            continue
        source_type = current[0][1].upper()
        record = _record(kind=RIS_TYPES.get(source_type, 'other'))
        if source_type not in RIS_TYPES:
            warnings.append(f'Record {len(records) + 1}: unsupported RIS type {source_type}; retained as other.')
        authors, editors, first, last = [], [], '', ''
        for field, content in current[1:]:
            if field in {'AU', 'A1'}:
                authors.append(content)
            elif field == 'A2':
                if source_type == 'BOOK':
                    editors.append(content)
                else:
                    warnings.append(f'Record {len(records) + 1}: ambiguous A2 secondary-person role omitted; editor role was not inferred.')
            elif field == 'SP':
                first = content
            elif field == 'EP':
                last = content
            elif field == 'SN':
                record['issn' if record['type'] == 'journal_article' else 'isbn'] = content
            elif field in RIS_FIELDS:
                destination = RIS_FIELDS[field]
                if field == 'T2' and record['type'] == 'book_chapter':
                    destination = 'booktitle'
                if record.get(destination):
                    warnings.append(f'Record {len(records) + 1}: duplicate {destination}; first value retained.')
                else:
                    record[destination] = content
            else:
                warnings.append(f'Record {len(records) + 1}: unsupported RIS field {field} omitted.')
        if first:
            record['pages'] = first + ('-' + last if last else '')
        elif last:
            warnings.append(f'Record {len(records) + 1}: end page without start page; EP omitted.')
        _set_authors(record, authors)
        if editors:
            record['editors'] = '; '.join(editors)
        records.append(record)
        if len(records) > MAX_RECORDS:
            raise BibliographyError(f'Bibliographies support at most {MAX_RECORDS} records.')
        current, previous = None, None
    if current is not None:
        raise BibliographyError('RIS record is missing its ER terminator.')
    return records, warnings


def parse_bibliography(text, format):
    if not isinstance(text, str) or len(text) > MAX_TEXT or '\x00' in text:
        raise BibliographyError(f'Bibliography must be text of at most {MAX_TEXT:,} characters without NUL.')
    format = format.lower().lstrip('.')
    if format in {'bib', 'bibtex'}:
        reader = _BibReader(text.lstrip('\ufeff'))
        records = reader.parse()
        warnings = reader.warnings
        record_warnings = reader.record_warnings
    elif format == 'ris':
        records, warnings = _parse_ris(text.lstrip('\ufeff'))
        record_warnings = [[warning for warning in warnings if warning.startswith('Record ' + str(number) + ':')] for number in range(1, len(records) + 1)]
    else:
        raise BibliographyError('Choose BibTeX or RIS bibliography input.')
    if not records:
        warnings.append('No bibliography records found.')
    return {'records': records, 'warnings': warnings, 'record_warnings': record_warnings}


def _line(value):
    return re.sub(r'[\r\n\x00]+', ' ', str(value)).strip()


def export_ris(records):
    types = {kind: tag for tag, kind in RIS_TYPES.items()}
    fields = {'id': 'ID', 'title': 'TI', 'year': 'PY', 'journal': 'JO',
              'journal_abbreviation': 'JA', 'volume': 'VL', 'issue': 'IS',
              'doi': 'DO', 'url': 'UR', 'publisher': 'PB', 'publisher_place': 'CY',
              'booktitle': 'T2', 'edition': 'ET', 'abstract': 'AB', 'note': 'N1'}
    output = []
    for record in records:
        output.append('TY  - ' + types.get(record.get('type'), 'GEN'))
        names = record.get('author_list', [])
        for author in names:
            value = author.get('literal') or (author.get('family', '') + (', ' + author['given'] if author.get('given') else ''))
            if value:
                output.append('AU  - ' + _line(value))
        if not names and record.get('authors'):
            # One opaque literal name: no unreported splitting into people.
            output.append('AU  - ' + _line(record['authors']))
        if record.get('type') == 'book' and record.get('editors'):
            output.append('A2  - ' + _line(record['editors']))
        for field, tag in fields.items():
            if record.get(field):
                output.append(tag + '  - ' + _line(record[field]))
        if record.get('pages'):
            pages = _line(record['pages'])
            match = re.fullmatch(r'([A-Za-z]*\d+)(?:--?|–)([A-Za-z]*\d+)', pages)
            output.append('SP  - ' + (match[1] if match else pages))
            if match:
                output.append('EP  - ' + match[2])
        for field in ('isbn', 'issn'):
            if record.get(field):
                output.append('SN  - ' + _line(record[field]))
        output.extend(['ER  -', ''])
    return '\n'.join(output)


def csl_records(records):
    types = {'journal_article': 'article-journal', 'book': 'book',
             'book_chapter': 'chapter', 'report': 'report', 'thesis': 'thesis'}
    fields = {'title': 'title', 'doi': 'DOI', 'url': 'URL', 'volume': 'volume',
              'issue': 'issue', 'pages': 'page', 'publisher': 'publisher',
              'publisher_place': 'publisher-place', 'edition': 'edition',
              'isbn': 'ISBN', 'issn': 'ISSN', 'abstract': 'abstract', 'note': 'note',
              'institution': 'institution', 'report_number': 'number', 'thesis_type': 'genre'}
    output = []
    for record in records:
        item = {'id': str(record.get('id', '')), 'type': types.get(record.get('type'), 'document')}
        for source, target in fields.items():
            if record.get(source):
                item[target] = record[source]
        container = record.get('booktitle') or record.get('journal')
        if container:
            item['container-title'] = container
        if record.get('journal_abbreviation'):
            item['container-title-short'] = record['journal_abbreviation']
        if record.get('author_list'):
            item['author'] = [dict(author) for author in record['author_list']]
        elif record.get('authors'):
            item['author'] = [{'literal': record['authors']}]
        if record.get('editors'):
            item['editor'] = [{'literal': record['editors']}]
        if record.get('year'):
            year = str(record['year']).strip()
            item['issued'] = {'date-parts': [[int(year)]]} if re.fullmatch(r'\d{4}', year) else {'literal': year}
        output.append(item)
    return output


def export_csl_json(records):
    return json.dumps(csl_records(records), ensure_ascii=False, indent=2) + '\n'
