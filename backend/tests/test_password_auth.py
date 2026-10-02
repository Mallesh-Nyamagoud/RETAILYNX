"""Username + password authentication tests (bcrypt, SQLite, login throttle).

The user database is pointed at a throwaway SQLite file per test, so nothing
here touches the real data directory or the analytics (DuckDB) catalog.
"""
import gc
import shutil
import tempfile
import unittest
from pathlib import Path

from app.services import auth


class PasswordAuthTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="retailynx_auth_test_")
        self._saved = {
            "DATABASE_URL": auth.DATABASE_URL,
            "ADMIN_USERNAME": auth.ADMIN_USERNAME,
            "ADMIN_PASSWORD": auth.ADMIN_PASSWORD,
            "MAX_LOGIN_ATTEMPTS": auth.MAX_LOGIN_ATTEMPTS,
            "LOGIN_ATTEMPT_WINDOW_SECONDS": auth.LOGIN_ATTEMPT_WINDOW_SECONDS,
            "BCRYPT_ROUNDS": auth.BCRYPT_ROUNDS,
        }
        # bcrypt cost 4 keeps the suite fast; production uses 12 (see the module).
        auth.BCRYPT_ROUNDS = 4
        auth.DATABASE_URL = f"sqlite:///{(Path(self._tmpdir) / 'auth_test.db').as_posix()}"
        auth.ADMIN_USERNAME = "mis@adonisgroup.in"
        auth.ADMIN_PASSWORD = "ADONIS@13719"
        auth._engine = None
        auth.init_db()

    def tearDown(self):
        if auth._engine is not None:
            auth._engine.dispose()
        auth._engine = None
        for key, value in self._saved.items():
            setattr(auth, key, value)
        # Let GC release the SQLite file handle before removing the temp dir
        # (Windows keeps the file locked while any connection is open).
        gc.collect()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _fresh_blank_database(self):
        """Point the engine at a brand-new, completely empty SQLite file.

        Used by the tests that need to observe startup seeding from scratch
        (setUp has already seeded an admin in the default test database).
        """
        if auth._engine is not None:
            auth._engine.dispose()
        auth._engine = None
        self._db_seq = getattr(self, "_db_seq", 0) + 1
        blank = Path(self._tmpdir) / f"auth_blank_{self._db_seq}.db"
        auth.DATABASE_URL = f"sqlite:///{blank.as_posix()}"

    # --- hashing -----------------------------------------------------------
    def test_hash_is_bcrypt_salted_and_verifies(self):
        first = auth.hash_password("secret-password")
        second = auth.hash_password("secret-password")
        self.assertTrue(first.startswith("$2"))
        self.assertNotEqual(first, second)  # random salt -> different output
        self.assertTrue(auth.verify_password("secret-password", first))
        self.assertFalse(auth.verify_password("nope", first))
        self.assertFalse(auth.verify_password("secret-password", None))

    def test_legacy_pbkdf2_hash_still_verifies(self):
        import hashlib
        import secrets as pysecrets

        salt = pysecrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac("sha256", b"legacy-pw", bytes.fromhex(salt), 1000)
        legacy = f"pbkdf2_sha256$1000${salt}${digest.hex()}"
        self.assertTrue(auth.verify_password("legacy-pw", legacy))
        self.assertFalse(auth.verify_password("wrong", legacy))

    # --- bootstrap admin ---------------------------------------------------
    def test_bootstrap_admin_can_authenticate(self):
        user = auth.authenticate("mis@adonisgroup.in", "ADONIS@13719")
        self.assertIsNotNone(user)
        self.assertEqual(user["role"], "ADMIN")
        self.assertTrue(user["is_active"])
        self.assertNotIn("password_hash", user)

    def test_bootstrap_admin_is_not_recreated_when_one_exists(self):
        admin = auth.authenticate("mis@adonisgroup.in", "ADONIS@13719")
        auth.set_password(admin["id"], "rotated-password")
        # Re-running startup must NOT reset the rotated password.
        auth.init_db()
        self.assertIsNone(auth.authenticate("mis@adonisgroup.in", "ADONIS@13719"))
        self.assertIsNotNone(auth.authenticate("mis@adonisgroup.in", "rotated-password"))

    def test_missing_admin_env_does_not_create_an_admin(self):
        """With no ADMIN_USERNAME/ADMIN_PASSWORD the app still starts, but no
        admin is seeded (so a misconfigured deploy fails at login, loudly)."""
        self._fresh_blank_database()
        auth.ADMIN_USERNAME = ""
        auth.ADMIN_PASSWORD = ""
        auth.init_db()
        self.assertEqual(auth.get_all_users(), [])

    # --- login -------------------------------------------------------------
    def test_username_is_case_insensitive_and_trimmed(self):
        self.assertIsNotNone(auth.authenticate("  MIS@AdonisGroup.in  ", "ADONIS@13719"))

    def test_wrong_password_and_unknown_user_rejected(self):
        self.assertIsNone(auth.authenticate("mis@adonisgroup.in", "wrong"))
        self.assertIsNone(auth.authenticate("nobody@company.com", "ADONIS@13719"))

    def test_deactivated_user_cannot_authenticate(self):
        user = auth.authenticate("mis@adonisgroup.in", "ADONIS@13719")
        auth.update_user_status(user["id"], False)
        self.assertIsNone(auth.authenticate("mis@adonisgroup.in", "ADONIS@13719"))

    def test_failed_attempts_lock_the_account(self):
        auth.MAX_LOGIN_ATTEMPTS = 3
        for _ in range(3):
            self.assertIsNone(auth.authenticate("mis@adonisgroup.in", "wrong"))
        # Locked out: even the CORRECT password is refused now.
        self.assertTrue(auth.is_locked_out("mis@adonisgroup.in"))
        self.assertIsNone(auth.authenticate("mis@adonisgroup.in", "ADONIS@13719"))

        auth.clear_failed_attempts("mis@adonisgroup.in")
        self.assertFalse(auth.is_locked_out("mis@adonisgroup.in"))
        self.assertIsNotNone(auth.authenticate("mis@adonisgroup.in", "ADONIS@13719"))

    def test_a_successful_login_forgives_earlier_failures(self):
        auth.MAX_LOGIN_ATTEMPTS = 3
        self.assertIsNone(auth.authenticate("mis@adonisgroup.in", "wrong"))
        self.assertIsNone(auth.authenticate("mis@adonisgroup.in", "wrong"))
        self.assertIsNotNone(auth.authenticate("mis@adonisgroup.in", "ADONIS@13719"))
        self.assertFalse(auth.is_locked_out("mis@adonisgroup.in"))

    # --- admin user management --------------------------------------------
    def test_add_user_with_password_never_leaks_hash(self):
        created = auth.add_user("analyst", "USER", "pw123456")
        self.assertNotIn("password_hash", created)
        self.assertEqual(created["role"], "USER")
        self.assertIsNotNone(auth.authenticate("analyst", "pw123456"))
        for row in auth.get_all_users():
            self.assertNotIn("password_hash", row)

    def test_add_user_requires_a_unique_username(self):
        auth.add_user("analyst", "USER", "pw123456")
        with self.assertRaises(ValueError):
            auth.add_user("ANALYST", "USER", "pw123456")

    def test_add_user_rejects_unknown_roles(self):
        with self.assertRaises(ValueError):
            auth.add_user("analyst", "SUPERUSER", "pw123456")

    def test_set_password_resets_and_unlocks(self):
        user = auth.add_user("analyst", "USER", "pw123456")
        auth.MAX_LOGIN_ATTEMPTS = 2
        auth.record_failed_attempt("analyst")
        auth.record_failed_attempt("analyst")
        self.assertTrue(auth.is_locked_out("analyst"))

        auth.set_password(user["id"], "brand-new-pw")
        self.assertFalse(auth.is_locked_out("analyst"))
        self.assertIsNone(auth.authenticate("analyst", "pw123456"))
        self.assertIsNotNone(auth.authenticate("analyst", "brand-new-pw"))

    def test_change_role(self):
        user = auth.add_user("analyst", "USER", "pw123456")
        auth.update_user_role(user["id"], "ADMIN")
        self.assertEqual(auth.get_user_by_id(user["id"])["role"], "ADMIN")
        with self.assertRaises(ValueError):
            auth.update_user_role(user["id"], "NOPE")

    def test_count_admins_and_remove_user(self):
        admin = auth.get_user_by_username("mis@adonisgroup.in")
        self.assertEqual(auth.count_admins(), 1)
        self.assertEqual(auth.count_admins(exclude_id=admin["id"]), 0)
        other = auth.add_user("analyst", "USER", "pw123456")
        auth.remove_user(other["id"])
        self.assertIsNone(auth.get_user_by_id(other["id"]))

    # --- misc --------------------------------------------------------------
    def test_postgres_urls_are_rewritten_for_psycopg(self):
        self.assertEqual(
            auth.normalize_database_url("postgres://u:p@h:5432/db"),
            "postgresql+psycopg://u:p@h:5432/db",
        )
        self.assertEqual(
            auth.normalize_database_url("postgresql://u:p@h:5432/db"),
            "postgresql+psycopg://u:p@h:5432/db",
        )
        # An already-explicit URL is left alone.
        self.assertEqual(
            auth.normalize_database_url("postgresql+psycopg://u:p@h/db"),
            "postgresql+psycopg://u:p@h/db",
        )

    def test_blank_admin_env_values_are_treated_as_unset(self):
        """A blank/whitespace value must behave exactly like an unset one."""
        self._fresh_blank_database()
        auth.ADMIN_USERNAME = "   "
        auth.ADMIN_PASSWORD = ""
        auth.init_db()  # must not raise and must not create anything
        self.assertEqual(auth.get_all_users(), [])


if __name__ == "__main__":
    unittest.main()