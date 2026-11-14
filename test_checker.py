"""Regression coverage for natural-language extrema and trend rules."""
import unittest
from pathlib import Path

import checker
from interactive_agent import EvidenceAgent


class CheckerLanguageTests(unittest.TestCase):
    labels = ['Jan', 'Feb', 'Mar', 'Apr']
    series = {'sales': [100, 120, 90, 150]}

    def check_text(self, text, labels=None, series=None):
        labels = self.labels if labels is None else labels
        series = self.series if series is None else series
        return checker.check(text, labels, series, checker.facts(labels, series), 'units')

    def assert_finding(self, text, status, prefix, **kwargs):
        result = self.check_text(text, **kwargs)
        self.assertTrue(any(s.startswith(prefix + ':') for s in result[status]), (text, result))
        opposite = 'contradicted' if status == 'verified' else 'verified'
        self.assertFalse(any(s.startswith(prefix + ':') for s in result[opposite]), (text, result))
        return result

    def test_lowest_wording(self):
        for wording in (
            'Sales is the lowest in March.', 'Sales were lowest during Mar.',
            'Sales reached their minimum in March.', 'Sales hit a low in March.',
            'Sales bottomed out in March.', 'Sales reached a trough in March.',
            'March has the smallest sales.', 'The minimum for sales occurs in March.',
            'Sales has its fewest units in March.', 'Sales min is in March.',
        ):
            with self.subTest(wording=wording):
                self.assert_finding(wording, 'verified', 'Minimum')

    def test_incorrect_minimum_explains_actual_category(self):
        result = self.assert_finding('Sales is the lowest in March.', 'contradicted', 'Minimum',
                                     series={'sales': [10, 14, 18, 27]})
        self.assertIn('10 at Jan', '\n'.join(result['contradicted']))

    def test_highest_wording(self):
        for wording in (
            'Sales is highest in April.', 'Sales peaked in Apr.',
            'Sales reaches its maximum in April.', 'Sales hit a high in April.',
            'Sales reaches the top value in April.', 'Sales has the largest value in April.',
            'The greatest sales occur in April.', 'Sales max is in April.',
            'Sales reached a record high in April.', 'Sales reached their high point in April.',
        ):
            with self.subTest(wording=wording):
                self.assert_finding(wording, 'verified', 'Peak')
        self.assert_finding('Sales is highest in March.', 'contradicted', 'Peak')

    def test_ties_and_unique_claims(self):
        series = {'sales': [90, 120, 90, 150]}
        for text in ('Sales is lowest in January.', 'Sales is lowest in March.',
                     'Sales is lowest in January and March.'):
            self.assert_finding(text, 'verified', 'Minimum', series=series)
        self.assert_finding('Sales has its only minimum in January.', 'contradicted', 'Minimum', series=series)
        self.assert_finding('Sales is lowest in January and February.', 'contradicted', 'Minimum', series=series)

    def test_negated_extrema(self):
        self.assert_finding('Sales is not lowest in January.', 'verified', 'Minimum')
        self.assert_finding('Sales is not lowest in March.', 'contradicted', 'Minimum')
        self.assert_finding('Sales did not peak in March.', 'verified', 'Peak')
        self.assert_finding('The sales peak is not in April.', 'contradicted', 'Peak')

    def test_month_aliases_and_non_month_labels(self):
        self.assert_finding('Sales is lowest in MARCH.', 'verified', 'Minimum',
                            labels=['January', 'February', 'March', 'April'])
        self.assert_finding('Sales is lowest in Sept.', 'verified', 'Minimum',
                            labels=['Jun', 'Jul', 'September', 'Oct'])
        self.assert_finding('Sales is lowest at New York.', 'verified', 'Minimum',
                            labels=['Boston', 'Chicago', 'New York', 'Los Angeles'])
        self.assert_finding('Sales is lowest in Q3.', 'verified', 'Minimum',
                            labels=['Q1', 'Q2', 'Q3', 'Q4'])

    def test_extreme_value_and_category_must_both_match(self):
        self.assert_finding('Sales is lowest in March at 100.', 'contradicted', 'Minimum')
        self.assert_finding('Sales has a minimum of 90.', 'verified', 'Minimum')
        self.assert_finding('Sales has a maximum of 120.', 'contradicted', 'Peak')
        self.assert_finding('Sales has a minimum of -1,200.5 in March.', 'verified', 'Minimum',
                            series={'sales': [100, 120, -1200.5, 150]})

    def test_clause_subjects_do_not_bleed_between_series(self):
        result = self.check_text('Sales is lowest in March, while costs are highest in February.',
                                 series={'sales': [100, 120, 90, 150], 'costs': [10, 50, 20, 30]})
        self.assertEqual(len(result['verified']), 2, result)
        self.assertFalse(result['contradicted'], result)
        result = self.check_text('Sales is highest in April and lowest in March.')
        self.assertEqual(len(result['verified']), 2, result)
        result = self.check_text('Sales and costs are lowest in March.',
                                 series={'sales': [100, 120, 90, 150], 'costs': [10, 50, 2, 30]})
        self.assertEqual(len(result['verified']), 2, result)
        self.assertFalse(result['contradicted'], result)

    def test_series_names_are_literal_whole_names(self):
        result = self.check_text('Wholesale is lowest in March.', series={'sale': [1, 2, 3, 4]})
        self.assertFalse(result['verified'] or result['contradicted'])
        self.assertEqual(len(result['missing']), 1)
        self.assert_finding('Net sales (USD) is lowest in March.', 'verified', 'Minimum',
                            series={'net sales (usd)': [100, 120, 90, 150]})

    def test_unresolved_extrema_are_not_verified(self):
        for text in ('Sales is lowest in December.', 'Sales is lowest.',
                     'Sales is lowest in March or April.', 'Sales had the highest increase in March.'):
            with self.subTest(text=text):
                result = self.check_text(text)
                self.assertTrue(result['unverifiable'], result)
                self.assertFalse(result['verified'] or result['contradicted'], result)

    def test_predictions_are_not_verified_as_observations(self):
        for text in ('Sales will be lowest in March.', 'Sales might be highest in April.',
                     'If sales is lowest in March, something changes.'):
            with self.subTest(text=text):
                result = self.check_text(text)
                self.assertTrue(result['unverifiable'], result)
                self.assertFalse(result['verified'] or result['contradicted'], result)

    def test_trend_vocabulary_and_tenses(self):
        for wording in ('increased', 'rose', 'grew', 'climbed', 'went up', 'is rising',
                        'shows an upward trend', 'has been growing'):
            self.assert_finding(f'Sales {wording} overall.', 'verified', 'Trend')
        for wording in ('decreased', 'fell', 'declined', 'dropped', 'shrank', 'went down', 'is falling'):
            self.assert_finding(f'Sales {wording} overall.', 'contradicted', 'Trend')

    def test_continuous_trends_inspect_intermediate_values(self):
        self.assert_finding('Sales increased continuously.', 'contradicted', 'Trend')
        self.assert_finding('Sales rose steadily.', 'contradicted', 'Trend')
        self.assert_finding('Sales increased every month.', 'contradicted', 'Trend')
        self.assert_finding('Sales increased continuously.', 'verified', 'Trend',
                            series={'sales': [1, 2, 3, 4]})
        self.assert_finding('Sales dropped consistently.', 'verified', 'Trend',
                            series={'sales': [4, 3, 2, 1]})

    def test_local_trends_and_negation(self):
        self.assert_finding('Sales decreased from February to March.', 'verified', 'Trend')
        self.assert_finding('Sales increased between February and March.', 'contradicted', 'Trend')
        self.assert_finding('Sales dipped in March.', 'verified', 'Trend')
        self.assert_finding('Sales did not decrease overall.', 'verified', 'Trend')
        self.assert_finding('Sales did not increase overall.', 'contradicted', 'Trend')
        self.assert_finding('Sales did not increase continuously.', 'verified', 'Trend')

    def test_flat_trends(self):
        for wording in ('remained stable', 'stayed flat', 'was constant', 'did not change',
                        'remained the same'):
            self.assert_finding(f'Sales {wording}.', 'verified', 'Trend', series={'sales': [2, 2, 2, 2]})
        self.assert_finding('Sales remained stable.', 'contradicted', 'Trend', series={'sales': [2, 3, 1, 2]})
        self.assert_finding('Sales was unchanged overall.', 'verified', 'Trend', series={'sales': [2, 3, 1, 2]})
        self.assert_finding('Sales is not stable.', 'verified', 'Trend')

    def test_original_examples_still_have_expected_verdicts(self):
        examples = Path(__file__).parent / 'examples'
        labels, series, unit = checker.load(examples / 'chart1_data.csv')
        f = checker.facts(labels, series)
        correct = checker.check((examples / 'chart1_description_correct.txt').read_text(), labels, series, f, unit or 'units')
        self.assertFalse(correct['contradicted'] or correct['unverifiable'] or correct['missing'], correct)
        wrong = checker.check((examples / 'chart1_description_wrong.txt').read_text(), labels, series, f, unit or 'units')
        self.assertEqual(len(wrong['contradicted']), 4, wrong)
        self.assertEqual(len(wrong['unverifiable']), 1, wrong)

    def test_agent_explains_minimum_with_minimum_evidence(self):
        series = {'sales': [10, 14, 18, 27]}
        buckets = self.check_text('Sales is lowest in March.', series=series)
        agent = EvidenceAgent(self.labels, series, None, 'Sales is lowest in March.', buckets)
        finding = next(f for f in agent.findings if f.status == 'contradicted')
        self.assertEqual(finding.kind, 'minimum')
        result = agent.inspect(finding.id)
        self.assertIn('Source minimum for sales: 10 at Jan.', result['answer'])


if __name__ == '__main__':
    unittest.main()
