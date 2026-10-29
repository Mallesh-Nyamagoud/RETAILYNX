"""User accounts, password hashing and login throttling.

Storage is chosen by ``DATABASE_URL``:

* ``postgresql://`` / ``postgres://`` -> PostgreSQL. Cloud Run is deployed with
  an external Postgres because a container's disk is ephemeral and would lose
  every account (and every password reset) on each restart/scale event.
* anything else (the default) -> a SQLite file under ``DATA_DIR``, which is the
  zero-setup local-dev option.

Only password *hashes* are ever stored - bcrypt (``$2b$...``). Hashes produced
by the older PBKDF2 implementation are still accepted and are transparently
upgraded to bcrypt on the next successful login, so an existing database keeps
working with no migration step.
"""
from __future__ import annotations

import hashlib
import logging
import os
import secrets
import threading
import time
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import bcrypt
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    delete,
    func,
    insert,
    inspect,
    select,
    update,
)

from app.core.config import ADMIN_PASSWORD, ADMIN_USERNAME, DATABASE_URL

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------
# bcrypt cost. 12 rounds costs roughly a quarter of a second on a Cloud Run
# vCPU: slow enough to make offline cracking expensive, fast enough for an
# interactive login. Overridable so slow local machines and the test-suite can
# drop to the minimum.
try:
    BCRYPT_ROUNDS = max(4, min(15, int(os.environ.get("BCRYPT_ROUNDS", "12"))))
except ValueError:
    BCRYPT_ROUNDS = 12


def _int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, str(default))))
    except (TypeError, ValueError):
        return default


# Failed-login throttle: after MAX_LOGIN_ATTEMPTS failures inside the attempt
# window, the account is refused for LOGIN_LOCKOUT_SECONDS.
MAX_LOGIN_ATTEMPTS = _int_env("MAX_LOGIN_ATTEMPTS", 5)
LOGIN_LOCKOUT_SECONDS = _int_env("LOGIN_LOCKOUT_SECONDS", 900)
LOGIN_ATTEMPT_WINDOW_SECONDS = _int_env("LOGIN_ATTEMPT_WINDOW_SECONDS", 900)

# bcrypt only ever consumes the first 72 bytes of its input.
_BCRYPT_MAX_BYTES = 72

# Legacy PBKDF2 hashes (produced before the switch to bcrypt).
_PBKDF2_ALGO = "pbkdf2_sha256"

VALID_ROLES = ("ADMIN", "USER")
_USERNAME_MAX_LENGTH = 150


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
metadata = MetaData()

users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("username", String(_USERNAME_MAX_LENGTH), nullable=False, unique=True, index=True),
    Column("role", String(20), nullable=False, server_default="USER"),
    Column("is_active", Boolean, nullable=False, server_default="1"),
    Column("password_hash", String(255)),
    Column("google_sub", String(255)),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

# One row per failed login. Kept deliberately tiny and pruned on every write.
usage_sessions = Table(
    "usage_sessions", metadata,
    Column("id", String(64), primary_key=True),
    Column("user_id", Integer, nullable=False, index=True),
    Column("username", String(_USERNAME_MAX_LENGTH), nullable=False),
    Column("login_at", Integer, nullable=False), Column("logout_at", Integer),
    Column("last_seen_at", Integer, nullable=False),
    Column("interaction_count", Integer, nullable=False, server_default="0"),
    Column("auth_method", String(20), nullable=False, server_default="password"),
    Column("google_email", String(255)),
)

login_attempts = Table(
    "login_attempts",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("username", String(_USERNAME_MAX_LENGTH), nullable=False, index=True),
    Column("attempted_at", Integer, nullable=False),  # epoch seconds (portable)
)


def normalize_database_url(url: str) -> str:
    """Make a bare ``postgres://`` URL usable by SQLAlchemy 2.x.

    Cloud providers still hand out ``postgres://`` URLs, a scheme SQLAlchemy 2
    dropped. Rewriting it to ``postgresql+psycopg://`` also pins the psycopg 3
    driver explicitly instead of relying on dialect auto-detection.
    """
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


_engine = None
_engine_lock = threading.Lock()


def get_engine():
    """Process-wide SQLAlchemy engine for the user database (lazy singleton).

    ``pool_pre_ping`` transparently replaces connections that a managed
    Postgres (Cloud SQL) has dropped while the instance sat idle at
    min-instances=0.
    """
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                url = normalize_database_url(DATABASE_URL)
                kwargs: dict[str, Any] = {"pool_pre_ping": True}
                if url.startswith("sqlite"):
                    db_path = url.split("///", 1)[-1]
                    if db_path and db_path != ":memory:":
                        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
                    # FastAPI serves requests from a threadpool.
                    kwargs["connect_args"] = {"check_same_thread": False}
                log.info("User database: %s", "PostgreSQL" if url.startswith("postgresql") else url)
                _engine = create_engine(url, **kwargs)
    return _engine


# ---------------------------------------------------------------------------
# Usernames & passwords
# ---------------------------------------------------------------------------
def normalize_username(username: str | None) -> str:
    """Trim + lower-case a username so logins are case-insensitive."""
    return (username or "").strip().lower()


def _password_bytes(password: str) -> bytes:
    """bcrypt only uses the first 72 bytes of its input (and rejects longer)."""
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    """Return a salted bcrypt hash string for `password`."""
    return bcrypt.hashpw(_password_bytes(password), bcrypt.gensalt(BCRYPT_ROUNDS)).decode("ascii")


def verify_password(password: str, stored: str | None) -> bool:
    """Check `password` against a stored hash (bcrypt, or legacy PBKDF2)."""
    if not stored:
        return False
    stored = stored.strip()
    if stored.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            return bcrypt.checkpw(_password_bytes(password), stored.encode("ascii"))
        except ValueError:
            return False

    # Legacy PBKDF2-HMAC-SHA256 hash from a pre-bcrypt deployment.
    try:
        algo, iterations, salt, digest = stored.split("$")
        if algo != _PBKDF2_ALGO:
            return False
        expected = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations)
        )
    except (ValueError, TypeError):
        return False
    return secrets.compare_digest(expected.hex(), digest)


def _needs_rehash(stored: str | None) -> bool:
    """True for a missing/legacy/cheaper-than-configured hash."""
    if not stored or not stored.startswith(("$2a$", "$2b$", "$2y$")):
        return True
    try:
        return int(stored.split("$")[2]) < BCRYPT_ROUNDS
    except (IndexError, ValueError):
        return True


def _public(row: Mapping | None) -> dict | None:
    """Row -> dict without the password hash (the hash never leaves the server)."""
    if row is None:
        return None
    data = dict(row)
    data.pop("password_hash", None)
    data.pop("google_sub", None)  # stable provider identifier stays server-side
    if isinstance(data.get("created_at"), datetime):
        data["created_at"] = data["created_at"].isoformat()
    return data


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
def init_db() -> None:
    """Create the tables and seed the first ADMIN (exactly once)."""
    engine = get_engine()
    metadata.create_all(engine)
    _migrate_auth_columns(engine)
    _bootstrap_admin(engine)


def _migrate_auth_columns(engine) -> None:
    """Add optional Google identity/session fields to existing auth databases."""
    additions = {
        "users": {"google_sub": "VARCHAR(255)"},
        "usage_sessions": {
            "auth_method": "VARCHAR(20) NOT NULL DEFAULT 'password'",
            "google_email": "VARCHAR(255)",
        },
    }
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table_name, columns in additions.items():
            existing = {column["name"] for column in inspector.get_columns(table_name)}
            for name, definition in columns.items():
                if name not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {name} {definition}")
    from sqlalchemy import Index
    Index("ix_users_google_sub", users.c.google_sub, unique=True).create(engine, checkfirst=True)


def _bootstrap_admin(engine) -> None:
    """Create the bootstrap ADMIN from ADMIN_USERNAME / ADMIN_PASSWORD.

    Only runs while NO admin exists, so changing the environment variables
    after the first boot never silently resets a live administrator's password
    (use the User Access screen for that instead).
    """
    admin_username = normalize_username(ADMIN_USERNAME)
    if not admin_username or not ADMIN_PASSWORD:
        log.warning(
            "ADMIN_USERNAME/ADMIN_PASSWORD not set - no bootstrap admin was created. "
            "Set both and restart to seed the first administrator."
        )
        return

    with engine.begin() as conn:
        admin_count = conn.execute(
            select(func.count()).select_from(users).where(users.c.role == "ADMIN")
        ).scalar_one()
        if admin_count:
            log.info("An ADMIN already exists - leaving it untouched.")
            return
        existing = conn.execute(
            select(users.c.id).where(func.lower(users.c.username) == admin_username)
        ).first()
        if existing is not None:
            # A non-admin row occupies the bootstrap username: promote it.
            conn.execute(
                update(users)
                .where(users.c.id == existing[0])
                .values(role="ADMIN", is_active=True, password_hash=hash_password(ADMIN_PASSWORD))
            )
            log.info("Promoted existing user '%s' to the bootstrap ADMIN.", admin_username)
            return
        conn.execute(
            insert(users).values(
                username=admin_username,
                role="ADMIN",
                is_active=True,
                password_hash=hash_password(ADMIN_PASSWORD),
            )
        )
        log.info("Seeded the first ADMIN account '%s' from ADMIN_USERNAME.", admin_username)


# ---------------------------------------------------------------------------
# Login throttling (a simple failed-attempt limit)
# ---------------------------------------------------------------------------
def _prune_attempts(conn, now: int) -> None:
    """Drop attempt rows older than the counting window."""
    conn.execute(
        delete(login_attempts).where(
            login_attempts.c.attempted_at < now - LOGIN_ATTEMPT_WINDOW_SECONDS
        )
    )


def is_locked_out(username: str) -> bool:
    """True while `username` is inside the failed-attempt lockout window."""
    normalized = normalize_username(username)
    if not normalized:
        return False
    now = int(time.time())
    with get_engine().begin() as conn:
        _prune_attempts(conn, now)
        newest = conn.execute(
            select(func.max(login_attempts.c.attempted_at)).where(
                func.lower(login_attempts.c.username) == normalized
            )
        ).scalar()
        if newest is None or newest < now - LOGIN_LOCKOUT_SECONDS:
            return False
        recent = conn.execute(
            select(func.count())
            .select_from(login_attempts)
            .where(
                func.lower(login_attempts.c.username) == normalized,
                login_attempts.c.attempted_at >= now - LOGIN_ATTEMPT_WINDOW_SECONDS,
            )
        ).scalar_one()
    return recent >= MAX_LOGIN_ATTEMPTS


def record_failed_attempt(username: str) -> None:
    """Remember one failed login (for known and unknown usernames alike, so the
    lockout behaviour cannot be used to discover which accounts exist)."""
    normalized = normalize_username(username)
    if not normalized:
        return
    now = int(time.time())
    with get_engine().begin() as conn:
        conn.execute(insert(login_attempts).values(username=normalized, attempted_at=now))
        _prune_attempts(conn, now)


def clear_failed_attempts(username: str) -> None:
    """Forget every failed login for `username` (successful login / admin reset)."""
    normalized = normalize_username(username)
    if not normalized:
        return
    with get_engine().begin() as conn:
        conn.execute(
            delete(login_attempts).where(func.lower(login_attempts.c.username) == normalized)
        )


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------
def _fetch(conn, *, user_id: int | None = None, username: str | None = None) -> dict | None:
    stmt = select(users)
    if user_id is not None:
        stmt = stmt.where(users.c.id == user_id)
    else:
        stmt = stmt.where(func.lower(users.c.username) == normalize_username(username))
    return _public(conn.execute(stmt).mappings().first())


def get_user_by_username(username: str) -> dict | None:
    with get_engine().begin() as conn:
        return _fetch(conn, username=username)


def get_user_by_google_sub(google_sub: str) -> dict | None:
    with get_engine().begin() as conn:
        return _public(conn.execute(select(users).where(users.c.google_sub == google_sub)).mappings().first())


def link_google_sub(user_id: int, google_sub: str) -> None:
    with get_engine().begin() as conn:
        conn.execute(update(users).where(users.c.id == user_id).values(google_sub=google_sub))


def get_user_by_id(user_id: int) -> dict | None:
    with get_engine().begin() as conn:
        return _fetch(conn, user_id=user_id)


def get_all_users() -> list[dict]:
    with get_engine().begin() as conn:
        rows = conn.execute(select(users).order_by(users.c.id)).mappings().all()
    return [_public(row) for row in rows]


def start_usage_session(session_id: str, user: Mapping, auth_method: str = "password", google_email: str | None = None) -> None:
    now = int(time.time())
    with get_engine().begin() as conn:
        conn.execute(insert(usage_sessions).values(id=session_id, user_id=user["id"], username=user["username"], login_at=now, last_seen_at=now, interaction_count=0, auth_method=auth_method, google_email=google_email))


def record_interaction(session_id: str) -> None:
    now = int(time.time())
    with get_engine().begin() as conn:
        conn.execute(update(usage_sessions).where(usage_sessions.c.id == session_id, usage_sessions.c.logout_at.is_(None)).values(last_seen_at=now, interaction_count=usage_sessions.c.interaction_count + 1))


def end_usage_session(session_id: str) -> None:
    now = int(time.time())
    with get_engine().begin() as conn:
        conn.execute(update(usage_sessions).where(usage_sessions.c.id == session_id, usage_sessions.c.logout_at.is_(None)).values(logout_at=now, last_seen_at=now))


def get_usage_sessions(limit: int = 500) -> list[dict]:
    with get_engine().begin() as conn:
        rows = conn.execute(select(usage_sessions).order_by(usage_sessions.c.login_at.desc()).limit(limit)).mappings().all()
    now = int(time.time())
    result = []
    for row in rows:
        item = dict(row)
        item["duration_seconds"] = max(0, (item["logout_at"] or now) - item["login_at"])
        item["is_active"] = item["logout_at"] is None
        result.append(item)
    return result


def authenticate(username: str, password: str) -> dict | None:
    """Return the ACTIVE user when username + password are valid, else None.

    A lockout (or a wrong password) always returns None so the caller can only
    ever answer "invalid credentials" - it never leaks which half was wrong.
    """
    normalized = normalize_username(username)
    if not normalized or not password:
        return None
    if is_locked_out(normalized):
        log.warning("Login refused for '%s': too many failed attempts", normalized)
        return None

    with get_engine().begin() as conn:
        row = conn.execute(
            select(users).where(func.lower(users.c.username) == normalized)
        ).mappings().first()

    if row is None or not row["is_active"]:
        record_failed_attempt(normalized)
        return None
    if not verify_password(password, row["password_hash"]):
        record_failed_attempt(normalized)
        return None

    clear_failed_attempts(normalized)
    # Transparently move a legacy (PBKDF2) or cheaper bcrypt hash up to the
    # configured cost while we still hold the plaintext.
    if _needs_rehash(row["password_hash"]):
        set_password(row["id"], password)
    return _public(row)


# ---------------------------------------------------------------------------
# Mutations (used by the Admin "User Access" screen)
# ---------------------------------------------------------------------------
def add_user(username: str, role: str = "USER", password: str | None = None, google_sub: str | None = None) -> dict:
    """Create a user. `password` may be omitted, but the account then cannot
    sign in until an admin sets one."""
    normalized = normalize_username(username)
    if not normalized:
        raise ValueError("Username is required")
    if len(normalized) > _USERNAME_MAX_LENGTH:
        raise ValueError(f"Username must be at most {_USERNAME_MAX_LENGTH} characters")
    role = (role or "USER").upper()
    if role not in VALID_ROLES:
        raise ValueError(f"Role must be one of {', '.join(VALID_ROLES)}")

    password_hash = hash_password(password) if password else None
    try:
        with get_engine().begin() as conn:
            result = conn.execute(
                insert(users).values(
                    username=normalized, role=role, is_active=True, password_hash=password_hash, google_sub=google_sub
                )
            )
            new_id = result.inserted_primary_key[0]
    except Exception as exc:  # IntegrityError on both SQLite and PostgreSQL
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            raise ValueError(f"User '{normalized}' already exists") from exc
        raise
    created = get_user_by_id(new_id)
    if created is None:  # pragma: no cover - defensive
        raise RuntimeError("User was inserted but could not be read back")
    return created


def set_password(user_id: int, password: str) -> None:
    """Set/reset a password and unlock the account (clears failed attempts)."""
    new_hash = hash_password(password)
    with get_engine().begin() as conn:
        row = conn.execute(select(users.c.username).where(users.c.id == user_id)).first()
        if row is None:
            raise ValueError(f"No user with id {user_id}")
        conn.execute(
            update(users).where(users.c.id == user_id).values(password_hash=new_hash)
        )
    clear_failed_attempts(row[0])


def update_user_role(user_id: int, role: str) -> None:
    role = (role or "").upper()
    if role not in VALID_ROLES:
        raise ValueError(f"Role must be one of {', '.join(VALID_ROLES)}")
    with get_engine().begin() as conn:
        conn.execute(update(users).where(users.c.id == user_id).values(role=role))


def update_user_status(user_id: int, is_active: bool) -> None:
    with get_engine().begin() as conn:
        conn.execute(update(users).where(users.c.id == user_id).values(is_active=bool(is_active)))


def count_admins(exclude_id: int | None = None) -> int:
    """How many ADMIN accounts there are (optionally ignoring one id)."""
    stmt = select(func.count()).select_from(users).where(users.c.role == "ADMIN")
    if exclude_id is not None:
        stmt = stmt.where(users.c.id != exclude_id)
    with get_engine().begin() as conn:
        return int(conn.execute(stmt).scalar_one())


def remove_user(user_id: int) -> None:
    with get_engine().begin() as conn:
        row = conn.execute(select(users.c.username).where(users.c.id == user_id)).first()
        conn.execute(delete(users).where(users.c.id == user_id))
    if row is not None:
        clear_failed_attempts(row[0])