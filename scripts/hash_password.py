"""Print an AUTH_USERS entry for one user (password read without echo).

    python scripts/hash_password.py alice staff
"""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
from smart_shared.passwords import ROLES, hash_password  # noqa: E402

if len(sys.argv) != 3 or sys.argv[2] not in ROLES:
    sys.exit("usage: python scripts/hash_password.py <username> <staff|viewer>")
password = getpass.getpass("Password: ")
if len(password) < 10:
    sys.exit("use at least 10 characters")
print(f"{sys.argv[1]}:{sys.argv[2]}:{hash_password(password)}")
