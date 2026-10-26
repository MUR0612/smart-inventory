"""Password hashing (stdlib only, so setup scripts need no extra packages)."""
import hashlib
import hmac
import secrets

ROLES = ("viewer", "staff")
PBKDF2_ITERATIONS = 600_000


def hash_password(password: str, iterations: int = PBKDF2_ITERATIONS, salt: bytes | None = None) -> str:
    # "." separators avoid "$", which Docker Compose would try to interpolate.
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256.{iterations}.{salt.hex()}.{digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = encoded.split(".")
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)
