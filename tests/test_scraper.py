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
    def test_optional_colors_fail_safely(self, get):
        for failure in (scraper.requests.Timeout(), scraper.requests.HTTPError()):
            get.side_effect = failure
            self.assertEqual(scraper.fetch_legacy_colors('https://www.profixio.com/example'), {})

    def test_legacy_url_and_merge_preserve_identity_and_last_color(self):
        self.assertEqual(scraper.legacy_color_url(MATCH_URL, MATCH_HTML),
                         'https://www.profixio.com/app/lx/competition/leagueid27939?expandmatch=32678592')
        teams = scraper.extract_team_colors(MATCH_HTML)
        scraper.merge_team_colors(teams, {'1592929': {'color': '#ff0000', 'name': 'Wrong'},
                                         '999': {'color': '#ffffff'}})
        scraper.merge_team_colors(teams, {'1592929': {'color': 'transparent'}})
        self.assertEqual(list(teams), ['1590006', '1592929'])
        self.assertEqual(teams['1592929'], {'color': '#FF0000', 'name': 'Vallentuna VBK B'})

    def test_overrides_reload_and_restore_automatic_colors(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'colors.json'
            for contents, expected in [('{"home":"#12ab34"}', '#12AB34'),
                                       ('{}', '#000000'), ('broken', '#000000'),
                                       ('{"home":"red"}', '#000000')]:
                path.write_text(contents)
                state = {'home': {'color': '#000000'}, 'away': {'color': '#FF0000'}}
                scraper.apply_color_overrides(state, str(path))
                self.assertEqual(state['home']['color'], expected)
                self.assertEqual(state['away']['color'], '#FF0000')

    @patch('scraper.time.sleep', side_effect=KeyboardInterrupt)
    @patch('scraper.ThreadPoolExecutor')
    @patch('scraper.requests.get')
    def test_pending_color_lookup_does_not_block_scoreboard(self, get, executor, sleep):
        executor.return_value.submit.return_value.done.return_value = False
        get.side_effect = [Mock(text=MATCH_HTML), Mock(json=Mock(return_value={
            'gamestate': {'currentScore': {'homeGoals': 0, 'awayGoals': 0},
                          'currentSetScores': [], 'period': 1}, 'events': [], 'lineup': [],
        }))]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'scoreboard.xml'
            self.assertEqual(scraper.main([MATCH_URL, '--daemon', '--output', str(output)]), 0)
            self.assertIn('Sollentuna VK C', output.read_text())
        executor.return_value.submit.assert_called_once()
        executor.return_value.submit.return_value.result.assert_not_called()

    @patch('scraper.requests.get')
    def test_new_url_writes_scoreboard(self, get):
        get.side_effect = [Mock(text=MATCH_HTML), Mock(text=""), Mock(json=Mock(return_value={
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
            score = json.loads((Path(directory) / 'scoreboard.json').read_text())
            self.assertEqual(score['home']['name'], 'Sollentuna VK C')
            self.assertEqual(score['away']['name'], 'Vallentuna VBK B')
            self.assertEqual((score['home']['sets'], score['home']['points']), (0, 0))
        self.assertEqual(get.call_args_list[2].args[0], API_URL)

    def test_scoreboard_json_mirrors_state_and_derives_sidecar_path(self):
        state = {
            'home': {'name': 'Sollentuna VK C', 'sets': 1, 'points': 14},
            'away': {'name': 'Vallentuna VBK B', 'sets': 2, 'points': 25},
            'matchEnded': True
        }
        with tempfile.TemporaryDirectory() as directory:
            xml_path = Path(directory) / 'scoreboard.xml'
            self.assertTrue(scraper.write_scoreboard_json(state, str(xml_path)))
            json_path = Path(directory) / 'scoreboard.json'
            self.assertTrue(json_path.exists())
            self.assertEqual(json.loads(json_path.read_text()), {
                'home': {'name': 'Sollentuna VK C', 'sets': 1, 'points': 14},
                'away': {'name': 'Vallentuna VBK B', 'sets': 2, 'points': 25},
                'matchEnded': True
            })

    def test_scoreboard_json_defaults_missing_fields_and_rejects_empty_state(self):
        with tempfile.TemporaryDirectory() as directory:
            xml_path = Path(directory) / 'scoreboard.xml'
            self.assertFalse(scraper.write_scoreboard_json(None, str(xml_path)))
            scraper.write_scoreboard_json({'home': {}, 'away': {}}, str(xml_path))
            score = json.loads((Path(directory) / 'scoreboard.json').read_text())
            self.assertEqual(score, {
                'home': {'name': 'Home', 'sets': 0, 'points': 0},
                'away': {'name': 'Away', 'sets': 0, 'points': 0},
                'matchEnded': False
            })


if __name__ == '__main__':
    unittest.main()
