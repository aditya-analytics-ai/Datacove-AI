"""
db.py - MySQL database layer for Datacove.

Replaces the SQLite implementation. Uses mysql-connector-python
(pure Python, no C deps - easier to install than mysqlclient).

Connection string read from .env:
    MYSQL_URL=mysql://user:password@host:3306/datacove

Tables created on first run:
  users      - auth, roles, active flag
  audit_log  - every mutating action
  sessions   - dataset metadata for "My Datasets" listing

Usage (identical to the SQLite version - zero changes needed in callers):
    from utils.db import db
    db.execute("SELECT ...", (params,))
    row = db.fetchone("SELECT ...", (params,))
    rows = db.fetchall("SELECT ...", (params,))
    db.log_audit(user_id, username, action, ...)
"""

from __future__ import annotations

from decimal import Decimal
import threading
import time
from typing import Any

from utils.logger import logger


# ── Row wrapper ───────────────────────────────────────────────────────────────
# sqlite3.Row lets you access columns by name (row["column"]).
# We replicate that behaviour so the rest of the code needs no changes.


class _Row(dict):
    """Dict subclass that supports both row["key"] and row[0] access."""

    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


def _json_safe(value):
    """Convert database values to JSON-serializable types."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value) if value % 1 else int(value)
    return value


def _convert_row(row: dict) -> _Row:
    """Convert row values to JSON-serializable types."""
    if row is None:
        return None
    return _Row({k: _json_safe(v) for k, v in row.items()})


# ── Database class ────────────────────────────────────────────────────────────


class Database:
    def __init__(self, url: str) -> None:
        self._url = url
        self._lock = threading.Lock()
        self._local = threading.local()  # per-thread connection
        self._migrate()

    # ── Connection management ─────────────────────────────────────────────────

    def _connect(self):
        """Return a live connection for the current thread, reconnecting if needed."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            try:
                conn.ping(reconnect=True, attempts=3, delay=1)
                return conn
            except Exception:
                pass

        import mysql.connector

        # Parse mysql://user:pass@host:port/dbname
        url = self._url
        if url.startswith("mysql://"):
            url = url[8:]
        # user:pass@host:port/db
        userinfo, hostinfo = url.rsplit("@", 1)
        user, password = userinfo.split(":", 1) if ":" in userinfo else (userinfo, "")
        hostport, database = hostinfo.split("/", 1)
        host, port = hostport.split(":", 1) if ":" in hostport else (hostport, "3306")

        conn = mysql.connector.connect(
            host=host,
            port=int(port),
            user=user,
            password=password,
            database=database,
            autocommit=False,
            charset="utf8mb4",
            collation="utf8mb4_unicode_ci",
            connection_timeout=10,
        )
        self._local.conn = conn
        return conn

    def _cursor(self):
        conn = self._connect()
        return conn.cursor(dictionary=True)

    # ── Schema migration ──────────────────────────────────────────────────────

    def _migrate(self) -> None:
        logger.info("DB: running schema migration")
        stmts = [
            # users
            """
            CREATE TABLE IF NOT EXISTS users (
                id            VARCHAR(36)  PRIMARY KEY,
                username      VARCHAR(64)  UNIQUE NOT NULL,
                password_hash TEXT         NOT NULL,
                role          VARCHAR(16)  NOT NULL DEFAULT 'user',
                is_active     TINYINT(1)   NOT NULL DEFAULT 1,
                created_at    DOUBLE       NOT NULL DEFAULT (UNIX_TIMESTAMP())
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
            # audit_log
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id          BIGINT       PRIMARY KEY AUTO_INCREMENT,
                user_id     VARCHAR(36)  NOT NULL,
                username    VARCHAR(64)  NOT NULL,
                action      VARCHAR(64)  NOT NULL,
                resource    VARCHAR(255),
                detail      TEXT,
                ip_address  VARCHAR(45),
                ts          DOUBLE       NOT NULL DEFAULT (UNIX_TIMESTAMP()),
                INDEX idx_audit_user (user_id),
                INDEX idx_audit_ts   (ts)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
            # sessions
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id            VARCHAR(36)  PRIMARY KEY,
                owner_id      VARCHAR(36)  NOT NULL,
                filename      VARCHAR(255) NOT NULL,
                `rows`        INT          NOT NULL DEFAULT 0,
                `columns`     INT          NOT NULL DEFAULT 0,
                health_score  DOUBLE,
                created_at    DOUBLE       NOT NULL,
                last_accessed DOUBLE       NOT NULL,
                INDEX idx_sessions_owner (owner_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
            # user_tiers
            """
            CREATE TABLE IF NOT EXISTS user_tiers (
                user_id VARCHAR(36) PRIMARY KEY,
                tier VARCHAR(32) NOT NULL DEFAULT 'free',
                stripe_customer_id VARCHAR(128)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
            # pipelines
            """
            CREATE TABLE IF NOT EXISTS pipelines (
                id VARCHAR(36) PRIMARY KEY,
                owner_id VARCHAR(36) NOT NULL,
                name VARCHAR(255) NOT NULL,
                steps TEXT NOT NULL,
                created_at DOUBLE NOT NULL,
                INDEX idx_pipelines_owner (owner_id),
                INDEX idx_pipelines_name (name)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
            # schedules
            """
            CREATE TABLE IF NOT EXISTS schedules (
                id          VARCHAR(36)  PRIMARY KEY,
                owner_id    VARCHAR(36)  NOT NULL,
                pipeline_id VARCHAR(36)  NOT NULL,
                session_id  VARCHAR(36)  NOT NULL,
                cron        VARCHAR(64)  NOT NULL,
                label       VARCHAR(255) NOT NULL DEFAULT '',
                enabled     TINYINT(1)   NOT NULL DEFAULT 1,
                last_run_at DOUBLE,
                next_run_at DOUBLE,
                created_at  DOUBLE       NOT NULL,
                INDEX idx_schedules_owner (owner_id),
                INDEX idx_schedules_enabled (enabled),
                INDEX idx_schedules_next (next_run_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
            # schedule_runs
            """
            CREATE TABLE IF NOT EXISTS schedule_runs (
                id          VARCHAR(36)  PRIMARY KEY,
                schedule_id VARCHAR(36)  NOT NULL,
                started_at  DOUBLE       NOT NULL,
                finished_at DOUBLE,
                `status`    VARCHAR(16)  NOT NULL DEFAULT 'pending',
                rows_before INT,
                rows_after  INT,
                error       TEXT,
                INDEX idx_runs_schedule (schedule_id),
                INDEX idx_runs_status (`status`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
            # webhooks
            """
            CREATE TABLE IF NOT EXISTS webhooks (
                id            VARCHAR(36)  PRIMARY KEY,
                owner_id      VARCHAR(36)  NOT NULL,
                pipeline_id   VARCHAR(36)  NOT NULL,
                label         VARCHAR(255) NOT NULL DEFAULT '',
                secret        VARCHAR(64)  NOT NULL,
                created_at    DOUBLE       NOT NULL,
                last_used_at  DOUBLE,
                trigger_count INT          NOT NULL DEFAULT 0,
                INDEX idx_webhooks_owner (owner_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
            # datasets (for API key access)
            """
            CREATE TABLE IF NOT EXISTS datasets (
                id          VARCHAR(36)  PRIMARY KEY,
                name        VARCHAR(255) NOT NULL,
                owner_id    VARCHAR(36)  NOT NULL,
                data        LONGTEXT,
                created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_datasets_owner (owner_id),
                INDEX idx_datasets_name (name)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
        ]

        # Additive column migrations for existing installs
        additive = [
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(16) NOT NULL DEFAULT 'user'",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active TINYINT(1) NOT NULL DEFAULT 1",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(255) DEFAULT NULL",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name VARCHAR(128) DEFAULT NULL",
        ]

        with self._lock:
            cur = self._cursor()
            for stmt in stmts:
                cur.execute(stmt)
            for stmt in additive:
                try:
                    cur.execute(stmt)
                except Exception:
                    pass  # column already exists
            self._local.conn.commit()
            cur.close()
        logger.info("DB: migration complete")

    # ── Write ─────────────────────────────────────────────────────────────────

    def execute(self, sql: str, params: tuple = ()):
        """Execute a write query. MySQL uses %s placeholders (not ?)."""
        sql = _to_mysql(sql)
        with self._lock:
            cur = self._cursor()
            try:
                cur.execute(sql, params)
                self._local.conn.commit()
                return cur.rowcount
            except Exception:
                self._local.conn.rollback()
                raise
            finally:
                cur.close()

    # ── Read ──────────────────────────────────────────────────────────────────

    def fetchone(self, sql: str, params: tuple = ()) -> _Row | None:
        sql = _to_mysql(sql)
        with self._lock:
            cur = self._cursor()
            try:
                cur.execute(sql, params)
                row = cur.fetchone()
                return _convert_row(row)
            finally:
                cur.close()

    def fetchall(self, sql: str, params: tuple = ()) -> list[_Row]:
        sql = _to_mysql(sql)
        with self._lock:
            cur = self._cursor()
            try:
                cur.execute(sql, params)
                return [_convert_row(r) for r in cur.fetchall()]
            finally:
                cur.close()

    # ── Audit ─────────────────────────────────────────────────────────────────

    def log_audit(
        self,
        user_id: str,
        username: str,
        action: str,
        resource: str | None = None,
        detail: str | None = None,
        ip_address: str | None = None,
    ) -> None:
        self.execute(
            """INSERT INTO audit_log
               (user_id, username, action, resource, detail, ip_address, ts)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, username, action, resource, detail, ip_address, time.time()),
        )


# ── Placeholder translator ────────────────────────────────────────────────────
# All existing queries use SQLite-style ? placeholders.
# MySQL requires %s - this translates transparently so callers need no changes.


def _to_mysql(sql: str) -> str:
    """Replace ? placeholders with %s for MySQL, respecting string literals."""
    result = []
    in_string = False
    escape_next = False

    for char in sql:
        if escape_next:
            result.append(char)
            escape_next = False
        elif char == "\\\\":
            result.append(char)
            escape_next = True
        elif char == "'":
            result.append(char)
            in_string = not in_string
        elif char == "?" and not in_string:
            result.append("%s")
        else:
            result.append(char)

    return "".join(result)


# ── Singleton ─────────────────────────────────────────────────────────────────


def _build_db() -> Database:
    from config import settings

    url = getattr(settings, "MYSQL_URL", None)
    if not url:
        raise RuntimeError(
            "\n\nMYSQL_URL is not set in your .env file.\n"
            "Add it like this:\n"
            "  MYSQL_URL=mysql://datacove_user:yourpassword@localhost:3306/datacove\n"
        )
    return Database(url)


db = _build_db()
