import os
import hashlib
import secrets
import sqlite3
from typing import Optional
from pathlib import Path

# Use SQLite for simple, reliable local authentication storage
# Separate from DuckDB analytics database
AUTH_DB_PATH = Path(os.environ.get("AUTH_DB_PATH", Path(__file__).resolve().parent.parent.parent / "data" / "auth.sqlite"))

# PBKDF2 parameters for password hashing (stdlib only - no extra dependency).
_PBKDF2_ALGO = "pbkdf2_sha256"
_PBKDF2_ITERATIONS = 260_000


def get_db():
    AUTH_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(AUTH_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Return a salted PBKDF2-HMAC-SHA256 hash string for `password`."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), _PBKDF2_ITERATIONS
    )
    return f"{_PBKDF2_ALGO}${_PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: Optional[str]) -> bool:
    """Constant-time check of `password` against a stored hash string."""
    if not stored:
        return False
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


def _public(row: Optional[sqlite3.Row]) -> Optional[dict]:
    """Row -> dict without the password hash (the hash never leaves the server)."""
    if row is None:
        return None
    data = dict(row)
    data.pop("password_hash", None)
    return data


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                role TEXT NOT NULL DEFAULT 'USER',
                is_active BOOLEAN NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Migration: add the password_hash column to pre-existing databases.
        existing = {r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "password_hash" not in existing:
            conn.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")

        # Bootstrap / repair the initial admin so there is always a way in.
        # On Render's free tier the SQLite file is ephemeral and is recreated on
        # every cold start, so this runs again each time the service wakes up.
        admin_email = os.environ.get("INITIAL_ADMIN_EMAIL", "admin@company.com").lower()
        admin_password = os.environ.get("INITIAL_ADMIN_PASSWORD")
        row = conn.execute(
            "SELECT id, password_hash FROM users WHERE email = ?", (admin_email,)
        ).fetchone()

        if row is None:
            conn.execute(
                "INSERT INTO users (email, role, password_hash) VALUES (?, 'ADMIN', ?)",
                (admin_email, hash_password(admin_password) if admin_password else None),
            )
            print(f"Bootstrapped auth database with initial admin: {admin_email}")
        elif admin_password and not row["password_hash"]:
            # Existing admin (e.g. created under the Google-OAuth era) with no
            # password yet - give it the configured one so password login works.
            conn.execute(
                "UPDATE users SET password_hash = ?, role = 'ADMIN' WHERE id = ?",
                (hash_password(admin_password), row["id"]),
            )
        conn.commit()

def get_user_by_email(email: str) -> Optional[dict]:
    with get_db() as conn:
        cursor = conn.execute("SELECT * FROM users WHERE email = ?", (email.lower(),))
        row = cursor.fetchone()
        return _public(row)

def get_user_by_id(user_id: int) -> Optional[dict]:
    with get_db() as conn:
        cursor = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        return _public(row)

def get_all_users():
    with get_db() as conn:
        cursor = conn.execute("SELECT * FROM users ORDER BY created_at DESC")
        return [_public(row) for row in cursor.fetchall()]

def authenticate(email: str, password: str) -> Optional[dict]:
    """Return the ACTIVE user when email + password are valid, else None."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email.lower(),)).fetchone()
    if row is None:
        return None
    record = dict(row)
    if not record.get("is_active"):
        return None
    if not verify_password(password, record.get("password_hash")):
        return None
    record.pop("password_hash", None)
    return record

def add_user(email: str, role: str = "USER", password: Optional[str] = None):
    with get_db() as conn:
        try:
            conn.execute(
                "INSERT INTO users (email, role, password_hash) VALUES (?, ?, ?)",
                (email.lower(), role, hash_password(password) if password else None),
            )
            conn.commit()
            return get_user_by_email(email.lower())
        except sqlite3.IntegrityError:
            raise ValueError(f"User {email} already exists")

def set_password(user_id: int, password: str):
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (hash_password(password), user_id),
        )
        conn.commit()

def update_user_status(user_id: int, is_active: bool):
    with get_db() as conn:
        conn.execute("UPDATE users SET is_active = ? WHERE id = ?", (1 if is_active else 0, user_id))
        conn.commit()

def remove_user(user_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()

