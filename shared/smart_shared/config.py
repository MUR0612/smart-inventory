"""Environment configuration contract shared by both services.

Compose (.env) and Kubernetes (ConfigMap + Secret) use exactly these names.
Missing required values raise ``ConfigError`` naming the variable but never
printing any value.
"""
import os

from sqlalchemy.engine import URL


class ConfigError(RuntimeError):
    pass


def require(name: str, min_length: int = 1) -> str:
    value = os.getenv(name, "")
    if not value:
        raise ConfigError(f"Missing required environment variable: {name}")
    if len(value) < min_length:
        raise ConfigError(f"Environment variable {name} must be at least {min_length} characters")
    if "CHANGE_ME" in value:
        raise ConfigError(f"Environment variable {name} still has the placeholder from .env.example")
    return value


def optional(name: str, default: str) -> str:
    return os.getenv(name) or default


def database_url():
    """DB_URL wins (used by unit tests with SQLite); otherwise build from parts."""
    explicit = os.getenv("DB_URL")
    if explicit:
        return explicit
    return URL.create(
        "mysql+pymysql",
        username=require("DB_USER"),
        password=require("DB_PASSWORD"),
        host=require("DB_HOST"),
        port=int(optional("DB_PORT", "3306")),
        database=require("DB_NAME"),
    )


def engine_kwargs(url) -> dict:
    """Connection options: short timeouts and UTC session time zone for MySQL."""
    if str(url).startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {
        "pool_pre_ping": True,
        "pool_recycle": 1800,
        "connect_args": {
            "connect_timeout": 3,
            "read_timeout": 10,
            "write_timeout": 10,
            "init_command": "SET time_zone = '+00:00'",
        },
    }


def redis_settings() -> dict:
    return {
        "host": optional("REDIS_HOST", "redis"),
        "port": int(optional("REDIS_PORT", "6379")),
        "socket_connect_timeout": float(optional("REDIS_TIMEOUT_SECONDS", "0.5")),
        "socket_timeout": float(optional("REDIS_TIMEOUT_SECONDS", "0.5")),
    }


def required_schema_version() -> int:
    """Readiness waits until db/migrate.py reached this version (0 disables the check)."""
    return int(optional("REQUIRED_SCHEMA_VERSION", "2"))


def cors_origins() -> list[str]:
    """Same-origin by default; only explicitly listed origins get CORS headers."""
    raw = os.getenv("CORS_ALLOWED_ORIGINS", "")
    return [o.strip() for o in raw.split(",") if o.strip()]
