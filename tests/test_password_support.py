"""Run with: python3 -m unittest discover -s tests -v"""

import json
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest

from werkzeug.security import check_password_hash, generate_password_hash


class PasswordSupportTests(unittest.TestCase):
    def setUp(self):
        # Exercise the application without reading or changing real users.json.
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        root = Path(__file__).resolve().parents[1]
        for name in ('server.py', 'generate_password.py', 'password_support.py'):
            shutil.copyfile(root / name, self.directory / name)

    def run_without_pbkdf2(self, script, run_name):
        return subprocess.run(
            [sys.executable, '-c', (
                'import hashlib, runpy, sys; '
                'del hashlib.pbkdf2_hmac; '
                f'sys.argv = [{script!r}, "test-password"]; '
                f'runpy.run_path({script!r}, run_name={run_name!r})'
            )],
            cwd=self.directory, capture_output=True, text=True, timeout=10,
        )

    def test_server_rejects_missing_pbkdf2_before_serving(self):
        for run_name in ('__main__', 'server'):
            with self.subTest(run_name=run_name):
                result = self.run_without_pbkdf2('server.py', run_name)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('missing hashlib.pbkdf2_hmac', result.stderr)
                self.assertIn('OpenSSL/_hashlib support', result.stderr)
                self.assertNotIn('Starting production server', result.stdout)
                self.assertNotIn('Loaded', result.stdout)

    def test_generator_explains_missing_pbkdf2(self):
        result = self.run_without_pbkdf2('generate_password.py', '__main__')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('missing hashlib.pbkdf2_hmac', result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        self.assertNotIn('Password hash:', result.stdout)

    def test_generated_hash_still_verifies(self):
        result = subprocess.run(
            [sys.executable, 'generate_password.py', 'test-password'],
            cwd=self.directory, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith('Password hash: '))
        password_hash = result.stdout.strip().partition('Password hash: ')[2]
        self.assertTrue(password_hash.startswith('pbkdf2:sha256:'))
        self.assertTrue(check_password_hash(password_hash, 'test-password'))
        self.assertFalse(check_password_hash(password_hash, 'wrong-password'))

    def test_login_accepts_existing_hash_and_rejects_wrong_password(self):
        users = {'users': {'test-user': {
            'password_hash': generate_password_hash(
                'test-password', method='pbkdf2:sha256:600000',
            ),
        }}}
        (self.directory / 'users.json').write_text(json.dumps(users))
        namespace = runpy.run_path(str(self.directory / 'server.py'))
        app = namespace['app']
        app.config.update(TESTING=True, SECRET_KEY='test-session-secret')
        client = app.test_client()

        response = client.post('/login', data={
            'username': 'test-user', 'password': 'wrong-password',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Incorrect username or password.', response.data)
        with client.session_transaction() as session:
            self.assertNotIn('username', session)
        self.assertEqual(len(namespace['LOGIN_ATTEMPTS']['127.0.0.1']), 1)

        response = client.post('/login', data={
            'username': 'test-user', 'password': 'test-password',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], '/test-user/control')
        with client.session_transaction() as session:
            self.assertEqual(session['username'], 'test-user')
        self.assertNotIn('127.0.0.1', namespace['LOGIN_ATTEMPTS'])


if __name__ == '__main__':
    unittest.main()
