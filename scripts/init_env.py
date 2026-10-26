"""Create a local .env with fresh random secrets (never overwrites by default).

    python scripts/init_env.py                      # writes .env and .env.credentials
    python scripts/init_env.py --env-file other.env --credentials-file other.credentials

Login passwords for the generated users are written to the credentials file
(git-ignored, local only) instead of being printed.
"""
import argparse
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "shared"))
from smart_shared.passwords import hash_password  # noqa: E402


def token(n: int = 32) -> str:
    return secrets.token_urlsafe(n)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--env-file", default=str(ROOT / ".env"))
    parser.add_argument("--credentials-file", default=str(ROOT / ".env.credentials"))
    parser.add_argument("--staff-user", default="admin")
    parser.add_argument("--viewer-user", default="viewer")
    parser.add_argument("--gateway-port", default="8080")
    parser.add_argument("--force", action="store_true", help="overwrite existing files")
    args = parser.parse_args()

    env_path, cred_path = Path(args.env_file), Path(args.credentials_file)
    for path in (env_path, cred_path):
        if path.exists() and not args.force:
            sys.exit(f"{path} already exists; use --force to replace it")

    staff_pw, viewer_pw = token(12), token(12)
    users = ",".join([f"{args.staff_user}:staff:{hash_password(staff_pw)}",
                      f"{args.viewer_user}:viewer:{hash_password(viewer_pw)}"])
    env = {
        "DB_NAME": "smart_inventory",
        "DB_USER": "inventory_app",
        "DB_PASSWORD": token(),
        "MYSQL_ROOT_PASSWORD": token(),
        "AUTH_SECRET": token(48),
        "SERVICE_TOKEN": token(),
        "AUTH_USERS": users,
        "GATEWAY_PORT": args.gateway_port,
        "GATEWAY_BIND": "0.0.0.0",
        "SEED_DEMO_DATA": "true",
    }
    env_path.write_text("".join(f"{k}={v}\n" for k, v in env.items()), encoding="utf-8")
    cred_path.write_text(f"STAFF_USER={args.staff_user}\nSTAFF_PASSWORD={staff_pw}\n"
                         f"VIEWER_USER={args.viewer_user}\nVIEWER_PASSWORD={viewer_pw}\n", encoding="utf-8")
    for path in (env_path, cred_path):
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    print(f"wrote {env_path} (secrets) and {cred_path} (login passwords); both are git-ignored")


if __name__ == "__main__":
    main()
