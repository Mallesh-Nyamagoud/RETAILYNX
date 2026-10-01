import os
import sqlite3
from typing import Optional
from pathlib import Path

# Use SQLite for simple, reliable local authentication storage
# Separate from DuckDB analytics database
AUTH_DB_PATH = Path(os.environ.get("AUTH_DB_PATH", Path(__file__).resolve().parent.parent.parent / "data" / "auth.sqlite"))

def get_db():
    AUTH_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(AUTH_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

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
        # If the table is empty, auto-create a default admin for bootstrapping
        # (This handles the requirement "How to create the first ADMIN user")
        cursor = conn.execute("SELECT COUNT(*) as count FROM users")
        if cursor.fetchone()["count"] == 0:
            default_admin = os.environ.get("INITIAL_ADMIN_EMAIL", "admin@company.com")
            conn.execute("INSERT INTO users (email, role) VALUES (?, 'ADMIN')", (default_admin,))
            print(f"Bootstrapped auth database with initial admin: {default_admin}")
        conn.commit()

def get_user_by_email(email: str) -> Optional[dict]:
    with get_db() as conn:
        cursor = conn.execute("SELECT * FROM users WHERE email = ?", (email,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_user_by_id(user_id: int) -> Optional[dict]:
    with get_db() as conn:
        cursor = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_all_users():
    with get_db() as conn:
        cursor = conn.execute("SELECT * FROM users ORDER BY created_at DESC")
        return [dict(row) for row in cursor.fetchall()]

def add_user(email: str, role: str = "USER"):
    with get_db() as conn:
        try:
            conn.execute("INSERT INTO users (email, role) VALUES (?, ?)", (email.lower(), role))
            conn.commit()
            return get_user_by_email(email.lower())
        except sqlite3.IntegrityError:
            raise ValueError(f"User {email} already exists")

def update_user_status(user_id: int, is_active: bool):
    with get_db() as conn:
        conn.execute("UPDATE users SET is_active = ? WHERE id = ?", (1 if is_active else 0, user_id))
        conn.commit()

def remove_user(user_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()

