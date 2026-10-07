"""Literal synthetic goldens for the pinned official CSL styles.

The official Vancouver/NLM parent specifies parentheses, minimal page ranges
and stripped journal periods. IEEE specifies typographic quotes, short journal
titles, conjunctions and no numeric collapse. APA styles journal and volume
separately. See vendor/csl/styles for the exact upstream rules and provenance.
"""
import unittest

from citations import CitationError, citation_key, format_reference, render_citations


def document(number=1, **metadata):
    fields = dict(title='Widgets', author_list=[{'family': 'Doe', 'given': 'Jane'}],
                  authors='Doe, Jane', year='2024', type='journal_article',
                  journal='Widget Review', journal_abbreviation='Widget Rev',
                  volume='3', issue='2', pages='10-20', doi='')
    fields.update(metadata)
    # Book/report/thesis fixtures must not accidentally carry journal fields.
    if fields['type'] != 'journal_article':
        for key in ('journal', 'journal_abbreviation', 'volume', 'issue'):
            if key not in metadata:
                fields[key] = ''
        if fields['type'] != 'book_chapter' and 'pages' not in metadata:
            fields['pages'] = ''
    return {'id': f'{number:032x}', 'name': f'synthetic{number}.pdf', 'kind': 'pdf', 'pages': 5, 'metadata': fields}


def marker(number=1, page=1):
    return '[[source:' + f'{number:032x}' + ':' + str(page) + ']]'


REFERENCE_GOLDENS = [
    ('vancouver_article', 'vancouver', {}, '1. Doe J. Widgets. Widget Rev. 2024;3(2):10–20.'),
    ('apa_article', 'apa', {}, 'Doe, J. (2024). Widgets. *Widget Review*, *3*(2), 10–20.'),
    ('ieee_article', 'ieee', {}, '[1] J. Doe, “Widgets,” *Widget Rev*, vol. 3, no. 2, pp. 10–20, 2024.'),
    ('vancouver_book', 'vancouver', dict(type='book', publisher='Example Press', publisher_place='Example City', edition='2'), '1. Doe J. Widgets. 2nd ed. Example City: Example Press; 2024.'),
    ('apa_book', 'apa', dict(type='book', publisher='Example Press', publisher_place='Example City', edition='2'), 'Doe, J. (2024). *Widgets* (2nd ed.). Example Press.'),
    ('ieee_book', 'ieee', dict(type='book', publisher='Example Press', publisher_place='Example City', edition='2'), '[1] J. Doe, *Widgets*, 2nd ed. Example City: Example Press, 2024.'),
    ('vancouver_chapter', 'vancouver', dict(type='book_chapter', booktitle='Widget Book', editors='J. Smith', publisher='Example Press', publisher_place='Example City'), '1. Doe J. Widgets. In: J. Smith, editor. Widget Book. Example City: Example Press; 2024. p. 10–20.'),
    ('apa_chapter', 'apa', dict(type='book_chapter', booktitle='Widget Book', editors='J. Smith', publisher='Example Press'), 'Doe, J. (2024). Widgets. In J. Smith (Ed.), *Widget Book* (pp. 10–20). Example Press.'),
    ('ieee_chapter', 'ieee', dict(type='book_chapter', booktitle='Widget Book', editors='J. Smith', publisher='Example Press', publisher_place='Example City'), '[1] J. Doe, “Widgets,” in *Widget Book*, J. Smith, Ed., Example City: Example Press, 2024, pp. 10–20.'),
    ('vancouver_report', 'vancouver', dict(type='report', publisher='Example Press', publisher_place='Example City', report_number='W1'), '1. Doe J. Widgets. Example City: Example Press; 2024. Report no.: W1.'),
    ('apa_report', 'apa', dict(type='report', publisher='Example Press', report_number='W1'), 'Doe, J. (2024). *Widgets* (No. W1). Example Press.'),
    ('ieee_report', 'ieee', dict(type='report', publisher='Example Press', publisher_place='Example City', report_number='W1'), '[1] J. Doe, “Widgets,” Example Press, Example City, W1, 2024.'),
    ('vancouver_thesis', 'vancouver', dict(type='thesis', institution='Example University', publisher_place='Example City'), '1. Doe J. Widgets. [Example City]: Example University; 2024.'),
    ('apa_thesis', 'apa', dict(type='thesis', institution='Example University'), 'Doe, J. (2024). *Widgets*. Example University.'),
    ('ieee_thesis', 'ieee', dict(type='thesis', institution='Example University', publisher_place='Example City'), '[1] J. Doe, “Widgets,” Example University, Example City, 2024.'),
    ('vancouver_other', 'vancouver', dict(type='other'), '1. Doe J. Widgets. 2024.'),
    ('apa_other', 'apa', dict(type='other'), 'Doe, J. (2024). *Widgets*.'),
    ('ieee_other', 'ieee', dict(type='other'), '[1] J. Doe, “Widgets,” 2024.'),
    ('vancouver_missing_issue', 'vancouver', dict(issue=''), '1. Doe J. Widgets. Widget Rev. 2024;3:10–20.'),
    ('apa_missing_year', 'apa', dict(year=''), 'Doe, J. (n.d.). Widgets. *Widget Review*, *3*(2), 10–20.'),
    ('vancouver_doi', 'vancouver', dict(doi='https://doi.org/10.1000/widget'), '1. Doe J. Widgets. Widget Rev. 2024;3(2):10–20. doi:10.1000/widget'),
    ('apa_doi', 'apa', dict(doi='doi: 10.1000/widget'), 'Doe, J. (2024). Widgets. *Widget Review*, *3*(2), 10–20. https://doi.org/10.1000/widget'),
    ('ieee_doi', 'ieee', dict(doi='10.1000/widget'), '[1] J. Doe, “Widgets,” *Widget Rev*, vol. 3, no. 2, pp. 10–20, 2024, doi: 10.1000/widget.'),
    ('vancouver_literal_group', 'vancouver', dict(author_list=[{'literal': 'Widget Group'}]), '1. Widget Group. Widgets. Widget Rev. 2024;3(2):10–20.'),
    ('apa_literal_group', 'apa', dict(author_list=[{'literal': 'Widget Group'}]), 'Widget Group. (2024). Widgets. *Widget Review*, *3*(2), 10–20.'),
    ('ieee_literal_group', 'ieee', dict(author_list=[{'literal': 'Widget Group'}]), '[1] Widget Group, “Widgets,” *Widget Rev*, vol. 3, no. 2, pp. 10–20, 2024.'),
    ('apa_no_author', 'apa', dict(author_list=[], authors=''), 'Widgets. (2024). *Widget Review*, *3*(2), 10–20.'),
    ('apa_hyphen_initials', 'apa', dict(author_list=[{'family': 'Lee', 'given': 'Anne-Marie'}]), 'Lee, A.-M. (2024). Widgets. *Widget Review*, *3*(2), 10–20.'),
]


class CitationGoldens(unittest.TestCase):
    def test_numbering_is_shared_across_all_texts_and_first_citation(self):
        value = render_citations([marker(2), marker(1) + ' then ' + marker(2)], [document(1), document(2)])
        self.assertEqual(value['texts'], ['(1)', '(2) then (1)'])
        self.assertEqual(value['cited_ids'], [f'{2:032x}', f'{1:032x}'])

    def test_vancouver_group_and_range(self):
        text = marker(3) + ', ' + marker(1) + ' ' + marker(2) + ' ' + marker(2)
        self.assertEqual(render_citations([text], [document(1), document(2), document(3)])['texts'], ['(1–3)'])

    def test_ieee_group_and_range(self):
        text = marker(1) + ', ' + marker(2) + ' ' + marker(3)
        self.assertEqual(render_citations([text], [document(1), document(2), document(3)], 'ieee')['texts'], ['[1], [2], [3]'])

    def test_vancouver_two_numbers_do_not_make_a_range(self):
        text = marker(1) + ' ' + marker(2)
        self.assertEqual(render_citations([text], [document(1), document(2)])['texts'], ['(1,2)'])

    def test_ieee_two_numbers(self):
        self.assertEqual(render_citations([marker(1) + ' ' + marker(2)], [document(1), document(2)], 'ieee')['texts'], ['[1], [2]'])

    def test_unknown_document_is_explicit_and_does_not_take_a_number(self):
        value = render_citations([marker(9) + ' then ' + marker(1)], [document()])
        self.assertEqual(value['texts'], ['[Unresolved source reference: ' + f'{9:032x}' + ':1] then (1)'])
        self.assertEqual(len(value['references']), 1)
        self.assertTrue(value['warnings'])

    def test_invalid_page_is_explicit(self):
        value = render_citations([marker(1, 6)], [document()])
        self.assertEqual(value['references'], [])
        self.assertIn('Unresolved source reference', value['texts'][0])

    def test_malformed_marker_is_explicit(self):
        value = render_citations(['[[source:bad:0]]'], [document()])
        self.assertEqual(value['texts'], ['[Unresolved source reference: bad:0]'])
        self.assertTrue(value['warnings'])

    def test_default_has_no_internal_file_locator(self):
        value = render_citations([marker(1, 3)], [document()])
        self.assertEqual(value['texts'], ['(1)'])
        self.assertEqual(value['evidence_locators'][0]['page'], 3)
        self.assertEqual(value['evidence_locators'][0]['marker'], marker(1, 3))

    def test_explicit_internal_locator(self):
        self.assertEqual(render_citations([marker(1, 3)], [document()], locator='internal')['texts'], ['(1) [source files: PDF p. 3]'])

    def test_explicit_text_unit_locator(self):
        item = document()
        item['kind'] = 'txt'
        self.assertEqual(render_citations([marker()], [item], locator='internal')['texts'], ['(1) [source files: text unit 1]'])

    def test_apa_one_author(self):
        self.assertEqual(render_citations([marker()], [document()], 'apa')['texts'], ['(Doe, 2024)'])

    def test_apa_two_authors(self):
        item = document(author_list=[{'family': 'Doe', 'given': 'Jane'}, {'family': 'Roe', 'given': 'John'}])
        self.assertEqual(render_citations([marker()], [item], 'apa')['texts'], ['(Doe & Roe, 2024)'])

    def test_apa_three_authors(self):
        item = document(author_list=[{'family': 'Doe', 'given': 'Jane'}, {'family': 'Roe', 'given': 'John'}, {'family': 'Smith', 'given': 'Anna'}])
        self.assertEqual(render_citations([marker()], [item], 'apa')['texts'], ['(Doe et al., 2024)'])

    def test_apa_group_sorted_by_author(self):
        items = [document(1, author_list=[{'literal': 'Zeta Group'}]), document(2, author_list=[{'literal': 'Alpha Group'}])]
        self.assertEqual(render_citations([marker(1) + ' ' + marker(2)], items, 'apa')['texts'], ['(Alpha Group, 2024; Zeta Group, 2024)'])

    def test_same_author_year_suffixes_follow_title_order(self):
        items = [document(1, title='Zeta widgets'), document(2, title='Alpha widgets')]
        value = render_citations([marker(1), marker(2)], items, 'apa')
        self.assertEqual(value['texts'], ['(Doe, 2024b)', '(Doe, 2024a)'])
        self.assertIn('(2024a). Alpha widgets.', value['references'][0])

    def test_different_author_lists_expand_not_false_suffixes(self):
        items = [document(1, author_list=[{'family': 'Doe', 'given': 'Jane'}, {'family': 'Roe', 'given': 'John'}, {'family': 'Smith', 'given': 'Anna'}]),
                 document(2, author_list=[{'family': 'Doe', 'given': 'Jane'}, {'family': 'Roe', 'given': 'John'}, {'family': 'Black', 'given': 'Anna'}])]
        self.assertEqual(render_citations([marker(1), marker(2)], items, 'apa')['texts'], ['(Doe, Roe, & Smith, 2024)', '(Doe, Roe, & Black, 2024)'])

    def test_doi_dedupe_normalizes_prefix_case(self):
        items = [document(1, doi='10.1000/Widget'), document(2, doi='https://doi.org/10.1000/widget')]
        value = render_citations([marker(1) + ' then ' + marker(2)], items)
        self.assertEqual(value['texts'], ['(1) then (1)'])
        self.assertEqual(len(value['references']), 1)
        self.assertEqual(len(value['cited_ids']), 2)

    def test_missing_doi_does_not_dedupe_by_title(self):
        self.assertEqual(len(render_citations([marker(1) + ' then ' + marker(2)], [document(1), document(2)])['references']), 2)

    def test_no_author_apa_uses_article_title(self):
        self.assertEqual(render_citations([marker()], [document(author_list=[], authors='')], 'apa')['texts'], ['(“Widgets,” 2024)'])

    def test_no_author_apa_uses_book_title_and_no_date(self):
        self.assertEqual(render_citations([marker()], [document(author_list=[], authors='', year='', type='book')], 'apa')['texts'], ['(*Widgets*, n.d.)'])

    def test_uncited_documents_are_not_in_references(self):
        self.assertEqual(len(render_citations([marker(1)], [document(1), document(2)])['references']), 1)

    def test_no_markers_no_references(self):
        self.assertEqual(render_citations(['Plain draft'], [document()])['references'], [])

    def test_original_inputs_remain_unchanged(self):
        text, item = marker(), document()
        render_citations([text], [item])
        self.assertEqual(text, marker())
        self.assertEqual(item['metadata']['title'], 'Widgets')

    def test_stable_full_id_key(self):
        self.assertEqual(citation_key(f'{1:032x}'), 'Kosh00000000000000000000000000000001')

    def test_invalid_style_and_locator_fail_explicitly(self):
        with self.assertRaises(CitationError):
            render_citations([], [], 'invalid')
        with self.assertRaises(CitationError):
            render_citations([], [], locator='publication_page_guess')

    def test_vancouver_six_authors_and_seven_et_al(self):
        names = [{'family': name, 'given': 'Jane'} for name in ('Able', 'Baker', 'Clark', 'Dunn', 'Evans', 'Fox', 'Gray')]
        self.assertEqual(format_reference(document(author_list=names[:6])['metadata'], 'vancouver'), '1. Able J, Baker J, Clark J, Dunn J, Evans J, Fox J. Widgets. Widget Rev. 2024;3(2):10–20.')
        self.assertEqual(format_reference(document(author_list=names)['metadata'], 'vancouver'), '1. Able J, Baker J, Clark J, Dunn J, Evans J, Fox J, et al. Widgets. Widget Rev. 2024;3(2):10–20.')

    def test_ieee_six_authors_and_seven_et_al(self):
        names = [{'family': name, 'given': 'Jane'} for name in ('Able', 'Baker', 'Clark', 'Dunn', 'Evans', 'Fox', 'Gray')]
        self.assertEqual(format_reference(document(author_list=names[:6])['metadata'], 'ieee'), '[1] J. Able, J. Baker, J. Clark, J. Dunn, J. Evans, and J. Fox, “Widgets,” *Widget Rev*, vol. 3, no. 2, pp. 10–20, 2024.')
        # Official IEEE author macro: et-al-min=7, use-first=1, italic et-al.
        self.assertEqual(format_reference(document(author_list=names)['metadata'], 'ieee'), '[1] J. Able *et al.*, “Widgets,” *Widget Rev*, vol. 3, no. 2, pp. 10–20, 2024.')

    def test_apa_twenty_authors_and_twenty_one_rule(self):
        names = [{'family': name, 'given': 'Jane'} for name in ('Able', 'Baker', 'Clark', 'Dunn', 'Evans', 'Fox', 'Gray', 'Hall', 'Irwin', 'Jones', 'King', 'Lee', 'Moore', 'Nash', 'Oaks', 'Page', 'Quinn', 'Reed', 'Stone', 'Tate', 'Underwood')]
        expected20 = 'Able, J., Baker, J., Clark, J., Dunn, J., Evans, J., Fox, J., Gray, J., Hall, J., Irwin, J., Jones, J., King, J., Lee, J., Moore, J., Nash, J., Oaks, J., Page, J., Quinn, J., Reed, J., Stone, J., & Tate, J. (2024). Widgets. *Widget Review*, *3*(2), 10–20.'
        expected21 = 'Able, J., Baker, J., Clark, J., Dunn, J., Evans, J., Fox, J., Gray, J., Hall, J., Irwin, J., Jones, J., King, J., Lee, J., Moore, J., Nash, J., Oaks, J., Page, J., Quinn, J., Reed, J., Stone, J., … Underwood, J. (2024). Widgets. *Widget Review*, *3*(2), 10–20.'
        self.assertEqual(format_reference(document(author_list=names[:20])['metadata'], 'apa'), expected20)
        self.assertEqual(format_reference(document(author_list=names)['metadata'], 'apa'), expected21)

    def test_apa_same_author_group_collapses_repeated_names(self):
        items = [document(1, title='Alpha'), document(2, title='Beta')]
        # Official APA citation sort keys omit title; equal author/year keys
        # preserve input order. Bibliography title sorting assigns a/b suffixes.
        self.assertEqual(render_citations([marker(2) + ', ' + marker(1)], items, 'apa')['texts'], ['(Doe, 2024b, 2024a)'])

    def test_apa_group_orders_multiple_years_under_one_author(self):
        items = [document(1, year='2024'), document(2, year='2023')]
        self.assertEqual(render_citations([marker(1) + ' ' + marker(2)], items, 'apa')['texts'], ['(Doe, 2023, 2024)'])

    def test_equal_surname_different_initials_are_distinguished(self):
        items = [document(1), document(2, author_list=[{'family': 'Doe', 'given': 'Peter'}])]
        self.assertEqual(render_citations([marker(1), marker(2)], items, 'apa')['texts'], ['(J. Doe, 2024)', '(P. Doe, 2024)'])

    def test_unclosed_source_marker_returns_warning(self):
        value = render_citations(['[[source:incomplete'], [document()])
        self.assertEqual(value['texts'], ['[Unresolved source reference: incomplete]'])
        self.assertTrue(value['warnings'])

    def test_same_doi_conflicting_metadata_warns_and_retains_first_cited(self):
        items = [document(1, doi='10.1000/x', title='Alpha'), document(2, doi='10.1000/x', title='Beta')]
        value = render_citations([marker(2) + ' then ' + marker(1)], items)
        self.assertEqual(value['texts'], ['(1) then (1)'])
        self.assertIn('Beta.', value['references'][0])
        self.assertTrue(any('conflicting title' in warning for warning in value['warnings']))

    def test_page_count_alias_and_unavailable_bounds_are_honest(self):
        item = document()
        item.pop('pages')
        item['page_count'] = 2
        self.assertEqual(render_citations([marker(1, 3)], [item])['references'], [])
        item.pop('page_count')
        self.assertTrue(any('bounds unavailable' in warning for warning in render_citations([marker()], [item])['warnings']))

    def test_repeated_marker_evidence_locator_is_deduplicated(self):
        value = render_citations([marker() + ' then ' + marker()], [document()])
        self.assertEqual(value['texts'], ['(1) then (1)'])
        self.assertEqual(len(value['evidence_locators']), 1)

    def test_single_newline_adjacent_markers_group_but_blank_paragraphs_do_not(self):
        items = [document(1), document(2)]
        value = render_citations([marker(1) + '\n' + marker(2), marker(1) + '\n\n' + marker(2)], items)
        self.assertEqual(value['texts'], ['(1,2)', '(1)\n\n(2)'])

    def test_apa_missing_date_suffix_uses_explicit_separator(self):
        items = [document(1, year='', title='Alpha'), document(2, year='', title='Beta')]
        value = render_citations([marker(1), marker(2)], items, 'apa')
        self.assertEqual(value['texts'], ['(Doe, n.d.-a)', '(Doe, n.d.-b)'])
        self.assertIn('(n.d.-a). Alpha.', value['references'][0])

    def test_nonconsecutive_numeric_cluster_remains_sorted(self):
        items = [document(index) for index in range(1, 7)]
        texts = [marker(index) for index in range(1, 7)] + [marker(6) + ' ' + marker(2) + ' ' + marker(3) + ' ' + marker(4)]
        self.assertEqual(render_citations(texts, items)['texts'][-1], '(2–4,6)')
        self.assertEqual(render_citations(texts, items, 'ieee')['texts'][-1], '[2], [3], [4], [6]')

    def test_document_reference_cites_without_a_page_or_evidence_locator(self):
        direct = '[[reference:' + f'{1:032x}' + ']]'
        item = document()
        item['pages'] = 0
        for style, expected in (('vancouver', '(1)'), ('ieee', '[1]'), ('apa', '(Doe, 2024)')):
            with self.subTest(style=style):
                value = render_citations([direct], [item], style)
                self.assertEqual(value['texts'], [expected])
                self.assertEqual(len(value['references']), 1)
                self.assertEqual(value['evidence_locators'], [])
                self.assertEqual(value['document_references'][0]['document_id'], item['id'])
                self.assertTrue(any('no source location' in warning for warning in value['warnings']))

    def test_document_and_true_page_one_share_reference_but_only_real_location(self):
        direct = '[[reference:' + f'{1:032x}' + ']]'
        value = render_citations([direct + ' then ' + marker()], [document()])
        self.assertEqual(value['texts'], ['(1) then (1)'])
        self.assertEqual(len(value['references']), 1)
        self.assertEqual(value['evidence_locators'][0]['page'], 1)
        self.assertEqual(value['evidence_locators'][0]['marker'], marker())
        self.assertEqual(len(value['document_references']), 1)

    def test_unknown_document_reference_is_explicit(self):
        value = render_citations(['[[reference:' + f'{9:032x}' + ']]'], [document()])
        self.assertEqual(value['texts'], ['[Unresolved document reference: ' + f'{9:032x}' + ']'])
        self.assertEqual(value['references'], [])

    def test_document_reference_rejects_invented_page_suffix(self):
        value = render_citations(['[[reference:' + f'{1:032x}' + ':1]]'], [document()])
        self.assertEqual(value['references'], [])
        self.assertEqual(value['evidence_locators'], [])
        self.assertTrue(value['warnings'])

    def test_document_reference_internal_mode_explicitly_has_no_location(self):
        direct = '[[reference:' + f'{1:032x}' + ']]'
        value = render_citations([direct], [document()], locator='internal')
        self.assertEqual(value['texts'], ['(1) [source files: document reference; no source location]'])
        self.assertEqual(value['evidence_locators'], [])

    def test_managed_figure_cannot_be_a_bibliographic_source(self):
        item = document()
        item['kind'] = 'png'
        for text in (marker(), '[[reference:' + f'{1:032x}' + ']]'):
            with self.subTest(text=text):
                value = render_citations([text], [item])
                self.assertEqual(value['references'], [])
                self.assertEqual(value['evidence_locators'], [])
                self.assertTrue(any('figure' in warning for warning in value['warnings']))


def _golden_test(style, changes, expected):
    def test(self):
        self.assertEqual(format_reference(document(**changes)['metadata'], style), expected)
    return test


for name, style, changes, expected in REFERENCE_GOLDENS:
    setattr(CitationGoldens, 'test_reference_' + name, _golden_test(style, changes, expected))


if __name__ == '__main__':
    unittest.main()
