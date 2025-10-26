#!/usr/bin/env python3
"""
Generate password hash for users.json
Usage: python3 generate_password.py <password>
"""
import sys
from werkzeug.security import generate_password_hash

if len(sys.argv) < 2:
    print("Usage: python3 generate_password.py <password>")
    sys.exit(1)

password = sys.argv[1]
hash_value = generate_password_hash(password, method='pbkdf2:sha256')
print(f"Password hash: {hash_value}")
