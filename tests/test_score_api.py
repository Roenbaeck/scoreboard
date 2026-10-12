"""Public API regressions, using isolated files and no production accounts."""
from html import escape
import json
from pathlib import Path
import runpy
import shutil
import tempfile
import unittest

import scraper
from score_status import format_status, read_score


def manual_xml(points=13, name='Å & Ö'):
    return ('<div id="scoreboard">'
            f'<div id="home_team">{escape(name)}</div><div id="away_team">Away</div>'
            '<div id="home_set">1</div><div id="away_set">2</div>'
            f'<div id="home_score">{points}</div><div id="away_score">25</div></div>')


class ScoreAPITests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        source = Path(__file__).resolve().parents[1]
        for name in ('server.py', 'password_support.py', 'score_status.py'):
            shutil.copyfile(source / name, self.root / name)
        (self.root / 'users.json').write_text(json.dumps({'users': {
            'test-user': {'token': 'test-token', 'password_hash': 'unused'},
        }}))
        namespace = runpy.run_path(str(self.root / 'server.py'))
        app = namespace['app']
        app.config.update(TESTING=True, SECRET_KEY='test-session')
        self.client = app.test_client()
        self.xml = self.root / 'data/test-user/scoreboard.xml'

    def upload(self, xml):
        response = self.client.post('/test-user/upload.php', data={
            'token': 'test-token', 'filename': 'scoreboard.xml', 'filedata': xml,
        })
        self.assertEqual(response.status_code, 200)

    def test_manual_score_is_available_without_running_scraper(self):
        self.upload(manual_xml())
        response = self.client.get('/test-user/api/status')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, 'text/plain; charset=utf-8')
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(response.get_data(as_text=True), '**Å \\& Ö – Away**\nSets: 1–2\n**Points: 13–25**')
        score = self.client.get('/test-user/api/score')
        self.assertEqual(score.json['home'], {'name': 'Å & Ö', 'sets': 1, 'points': 13})
        self.assertFalse(score.json['matchEnded'])
        self.assertEqual(score.headers['Cache-Control'], 'no-store')
        self.assertEqual(list(self.xml.parent.iterdir()), [self.xml])

    def test_manual_update_replaces_scraped_score_and_ignores_old_json(self):
        self.xml.parent.mkdir(parents=True)
        scraper.write_scoreboard_xml({
            'home': {'name': 'Home', 'sets': 1, 'points': 12},
            'away': {'name': 'Away', 'sets': 2, 'points': 25},
        }, str(self.xml))
        self.assertIn('Points: 12–25', self.client.get('/test-user/api/status').text)
        (self.xml.parent / 'scoreboard.json').write_text('{"obsolete": true}')
        self.upload(manual_xml(13))
        self.assertIn('Points: 13–25', self.client.get('/test-user/api/status').text)
        self.assertEqual(self.client.get('/test-user/api/score').json['home']['points'], 13)

    def test_scraped_final_score_omits_points_and_preserves_winner(self):
        self.xml.parent.mkdir(parents=True)
        scraper.write_scoreboard_xml({
            'home': {'name': 'Home & Friends', 'sets': 3, 'points': 25},
            'away': {'name': 'Away', 'sets': 2, 'points': 20}, 'matchEnded': True,
        }, str(self.xml))
        self.assertEqual(self.client.get('/test-user/api/status').text, '**Home \\& Friends – Away**\n**Final: 3–2**')
        score = self.client.get('/test-user/api/score').json
        self.assertTrue(score['matchEnded'])
        self.assertEqual(score['home']['points'], 0)

    def test_missing_unknown_and_invalid_user(self):
        for endpoint in ('status', 'score'):
            for user in ('test-user', 'unknown', 'UPPERCASE'):
                self.assertEqual(self.client.get(f'/{user}/api/{endpoint}').status_code, 404)

    def test_incomplete_oversized_invalid_utf8_and_ambiguous_scores(self):
        self.xml.parent.mkdir(parents=True)
        for data in (b'incomplete', b'x' * (256 * 1024 + 1), b'\xff',
                     manual_xml().replace('<div id="away_score">25</div>', '').encode(),
                     manual_xml().replace('>13<', '>oops<').encode(),
                     manual_xml().replace('</div>', '</div><div id="home_set">0</div>', 1).encode()):
            self.xml.write_bytes(data)
            for endpoint in ('status', 'score'):
                self.assertEqual(self.client.get(f'/test-user/api/{endpoint}').status_code, 503)

    def test_display_text_is_bounded_and_controls_cannot_add_fake_lines(self):
        self.upload(manual_xml(name='😀' * 1000 + '\n\x1b\u202e'))
        text = self.client.get('/test-user/api/status').text
        self.assertLessEqual(len(text.encode('utf-8')), 4096)
        self.assertLessEqual(len(text), 500)
        self.assertEqual(len(text.splitlines()), 3)
        self.assertNotIn('\x1b', text)
        self.assertNotIn('\u202e', text)

    def test_team_names_are_escaped_before_adding_markdown(self):
        name = '<b>*Team*</b> [A](B) &copy; _C_ `D` \\E'
        self.upload(manual_xml(name=name))
        response = self.client.get('/test-user/api/status')
        escaped = r'\<b\>\*Team\*\<\/b\> \[A\]\(B\) \&copy\; \_C\_ \`D\` \\E'
        self.assertEqual(response.text, f'**{escaped} – Away**\nSets: 1–2\n**Points: 13–25**')
        self.assertEqual(response.mimetype, 'text/plain')
        self.assertEqual(self.client.get('/test-user/api/score').json['home']['name'], name)

    def test_escaping_both_long_names_still_fits_watch_limits(self):
        text = format_status({
            'home': {'name': '*&' * 1000, 'sets': 999999, 'points': 999999},
            'away': {'name': '`[' * 1000, 'sets': 999999, 'points': 999999},
            'matchEnded': False,
        })
        self.assertLessEqual(len(text), 500)
        self.assertLessEqual(len(text.encode('utf-8')), 4096)
        self.assertEqual(len(text.splitlines()), 3)

    def test_parser_does_not_resolve_external_entities(self):
        self.xml.parent.mkdir(parents=True)
        self.xml.write_text('<!DOCTYPE doc [<!ENTITY leak SYSTEM "file:///no-access">]>'
                            + manual_xml(name='&leak;').replace('&amp;leak;', '&leak;'))
        self.assertEqual(read_score(self.xml)['home']['name'], '&leak')


if __name__ == '__main__':
    unittest.main()
