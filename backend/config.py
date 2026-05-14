"""
Datacove configuration - v5.

Changes from v4:
  - CORS_ORIGINS: replaces the hardcoded allow_origins=["*"] in main.py
  - JWT_SECRET validation: crashes at startup if still the placeholder
  - AUTH_ENABLED defaults to True for safety
  - ANTHROPIC_API_KEY added (was only OPENAI_API_KEY before)
"""
from pathlib import Path
import tempfile
import secrets
from pydantic_settings import BaseSettings

_BASE_DIR = Path(__file__).resolve().parent

_PLACEHOLDER = "change-me-in-production-use-a-long-random-string"


def _ensure_writable_dir(path: Path, fallback_name: str) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    probe = path / ".write_test"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return path
    except OSError:
        fallback = Path(tempfile.gettempdir()) / fallback_name
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


class Settings(BaseSettings):
    UPLOAD_DIR: Path = Path(tempfile.gettempdir()) / "datacove_uploads"
    DATASET_DIR: Path = _BASE_DIR / "datasets"
    MAX_UPLOAD_BYTES: int = 50 * 1024 * 1024
    MAX_ROWS: int = 1_000_000
    SESSION_TTL_SECONDS: int = 3600
    SESSION_MAX_COUNT: int = 200
    STREAM_CHUNK_SIZE: int = 50_000
    STREAM_THRESHOLD: int = 100_000
    ALLOWED_EXTENSIONS: str = ".csv,.xlsx,.xls"

    # AI
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    GOOGLE_API_KEY: str = ""
    GOOGLE_MODEL: str = "gemini-2.0-flash"
    AI_MAX_REQUESTS_PER_MINUTE: int = 10

    # Database
    MYSQL_URL: str = ""

    # Auth
    JWT_SECRET: str = _PLACEHOLDER
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60            # Access token: 1 hour
    JWT_REFRESH_EXPIRE_DAYS: int = 30       # Refresh token: 30 days
    AUTH_ENABLED: bool = True                # safe default: on

    # CORS - comma-separated list of allowed origins
    CORS_ORIGINS: str = "http://localhost:5173"

    # Frontend URL (used in password reset emails)
    FRONTEND_URL: str = "http://localhost:5173"

    # SMTP email (for password reset)
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASS: str = ""
    SMTP_FROM: str = "noreply@datacove.ai"
    SMTP_TLS:  str = "true"

    # Redis (for Celery job queue + Redis session store)
    REDIS_URL: str = ""   # e.g. redis://localhost:6379/0

    # Health score penalties
    PENALTY_DUPLICATE: int = 10
    PENALTY_MISSING_HIGH: int = 15
    PENALTY_MISSING_MED: int = 8
    PENALTY_MISSING_LOW: int = 3
    PENALTY_INVALID_FMT: int = 5
    PENALTY_MIXED_TYPES: int = 4
    PENALTY_WHITESPACE: int = 2

    class Config:
        env_file = _BASE_DIR / ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    def allowed_extensions_set(self) -> set:
        return {ext.strip() for ext in self.ALLOWED_EXTENSIONS.split(",")}

    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    def validate_secrets(self) -> None:
        """
        Call at startup. Raises RuntimeError if security-critical values
        are still at their insecure defaults.
        """
        if self.JWT_SECRET == _PLACEHOLDER or len(self.JWT_SECRET) < 32:
            raise RuntimeError(
                "\n\n"
                "  !! STARTUP BLOCKED - insecure JWT_SECRET detected !!\n"
                "  Set a real secret in your .env file:\n"
                "    JWT_SECRET=$(python -c \"import secrets; print(secrets.token_hex(32))\")\n"
                "  See .env.example for all required variables.\n"
            )
        # Warn (don't block) if CORS wildcard is combined with auth enabled.
        # Blocking startup here caused legitimate dev/staging setups to fail
        # when AUTH_ENABLED=True but CORS hadn't been tightened yet.
        # Operators should tighten CORS_ORIGINS in production.
        if "*" in self.cors_origins_list() and self.AUTH_ENABLED:
            import warnings
            warnings.warn(
                "\n\n"
                "  WARNING - CORS wildcard (*) is set while AUTH_ENABLED=True.\n"
                "  This is insecure for production. Set specific origins:\n"
                "    CORS_ORIGINS=https://app.yoursite.com\n",
                stacklevel=2,
            )


settings = Settings()
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
settings.DATASET_DIR = _ensure_writable_dir(settings.DATASET_DIR, "datacove_datasets")

# Flat exports for backward compatibility
UPLOAD_DIR            = settings.UPLOAD_DIR
MAX_UPLOAD_BYTES      = settings.MAX_UPLOAD_BYTES
MAX_ROWS              = settings.MAX_ROWS
ALLOWED_EXTENSIONS    = settings.allowed_extensions_set()
OPENAI_API_KEY        = settings.OPENAI_API_KEY
ANTHROPIC_API_KEY     = settings.ANTHROPIC_API_KEY
OPENAI_MODEL          = settings.OPENAI_MODEL
GOOGLE_API_KEY        = settings.GOOGLE_API_KEY
GOOGLE_MODEL          = settings.GOOGLE_MODEL
PENALTY_DUPLICATE     = settings.PENALTY_DUPLICATE
PENALTY_MISSING_HIGH  = settings.PENALTY_MISSING_HIGH
PENALTY_MISSING_MED   = settings.PENALTY_MISSING_MED
PENALTY_MISSING_LOW   = settings.PENALTY_MISSING_LOW
PENALTY_INVALID_FMT   = settings.PENALTY_INVALID_FMT
PENALTY_MIXED_TYPES   = settings.PENALTY_MIXED_TYPES
PENALTY_WHITESPACE    = settings.PENALTY_WHITESPACE
