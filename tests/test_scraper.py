"""Regression coverage for standalone and legacy Profixio match pages."""

from html import escape
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import scraper


MATCH_URL = 'https://www.profixio.com/app/lx/match/32678592'
API_URL = 'https://www.profixio.com/app/api/emp/32678592/0?expires=123&signature=test'
# Reduced from the new page's double-encoded Alpine attribute.
MATCH_HTML = r'''<div x-data="matchLive(JSON.parse('{\u0022kampId\u0022:32678592,\u0022resyncUrl\u0022:\u0022https:\\\/\\\/www.profixio.com\\\/app\\\/api\\\/emp\\\/32678592\\\/0?expires=123\\u0026signature=test\u0022}'))">
<a href="https://www.profixio.com/app/lx/competition/leagueid27939/teams/1590006">Sollentuna VK C</a>
<a href="https://www.profixio.com/app/lx/competition/leagueid27939/teams/1592929">Vallentuna VBK B</a>
</div>'''


class ProfixioTests(unittest.TestCase):
    def test_match_url_formats(self):
        for url in (MATCH_URL, MATCH_URL + '/', MATCH_URL + '?tab=events',
                    'https://www.profixio.com/app/lx/competition/leagueid27939?x=1&expandmatch=32678592'):
            with self.subTest(url=url):
                self.assertEqual(scraper.get_match_id(url), '32678592')
        for url in (MATCH_URL + '/extra', MATCH_URL.replace('32678592', 'invalid'),
                    'https://www.profixio.com/app?expandmatch='):
            self.assertIsNone(scraper.get_match_id(url))

    @patch('scraper.requests.get')
    def test_new_page_api_url(self, get):
        get.return_value = Mock(text=MATCH_HTML)
        self.assertEqual(scraper.get_api_url(MATCH_URL), (API_URL, MATCH_HTML))

    @patch('scraper.requests.get')
    def test_legacy_page_api_url(self, get):
        effects = {'scripts': {'match': "init({apiurl: '" + API_URL + "'})"}}
        html = '<div wire:effects="' + escape(json.dumps(effects), quote=True) + '"></div>'
        get.return_value = Mock(text=html)
        self.assertEqual(scraper.get_api_url(MATCH_URL)[0], API_URL)

    def test_malformed_config_is_ignored(self):
        self.assertEqual(scraper.extract_match_live_config(
            '''<div x-data="matchLive(JSON.parse('invalid'))"></div>'''), {})

    @patch('scraper.requests.get')
    def test_new_url_writes_scoreboard(self, get):
        get.side_effect = [Mock(text=MATCH_HTML), Mock(json=Mock(return_value={
            'gamestate': {'currentScore': {'homeGoals': 0, 'awayGoals': 0},
                          'currentSetScores': [], 'period': 1},
            'events': [], 'lineup': [],
        }))]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'scoreboard.xml'
            self.assertEqual(scraper.main([MATCH_URL, '--output', str(output), '--no-summary']), 0)
            xml = output.read_text()
            self.assertIn('Sollentuna VK C', xml)
            self.assertIn('Vallentuna VBK B', xml)
        self.assertEqual(get.call_args_list[1].args[0], API_URL)


if __name__ == '__main__':
    unittest.main()
