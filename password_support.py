"""Check the Python runtime required by Scoreboard's password hashes."""

import hashlib
import sys


def require_password_hashing():
    """Fail at startup if Python cannot generate or verify PBKDF2 hashes."""
    if not callable(getattr(hashlib, 'pbkdf2_hmac', None)):
        raise RuntimeError(
            f"Python at {sys.executable} is missing hashlib.pbkdf2_hmac, "
            "which Scoreboard needs to generate and verify passwords. "
            "Repair this Python installation's OpenSSL/_hashlib support "
            "or use a Python build with OpenSSL support. "
            "Run python3 -c 'import _hashlib' with the same interpreter "
            "to diagnose missing libraries. See README.md, Troubleshooting. "
            "Existing users.json password hashes do not need to be changed."
        )
