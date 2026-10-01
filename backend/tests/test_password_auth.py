import gc
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from app.services import auth


class PasswordAuthTests(unittest.TestCase):
    def setUp(self):
        # Point the auth store at a throwaway SQLite file for the test.
        self._tmpdir = tempfile.mkdtemp(prefix="retailynx_auth_test_")
        self._orig_db_path = auth.AUTH_DB_PATH
        auth.AUTH_DB_PATH = Path(self._tmpdir) / "auth_test.sqlite"

        self._env = {
            "INITIAL_ADMIN_EMAIL": "mis@adonisgroup.in",
            "INITIAL_ADMIN_PASSWORD": "ADONIS@13719",
        }
        self._saved_env = {k: os.environ.get(k) for k in self._env}
        os.environ.update(self._env)
        auth.init_db()

    def tearDown(self):
        auth.AUTH_DB_PATH = self._orig_db_path
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        # Let GC release the SQLite file handle before removing the temp dir
        # (Windows keeps the file locked while any connection is open).
        gc.collect()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_hash_is_salted_and_verifies(self):
        first = auth.hash_password("secret")
        second = auth.hash_password("secret")
        self.assertNotEqual(first, second)  # random salt -> different output
        self.assertTrue(auth.verify_password("secret", first))
        self.assertFalse(auth.verify_password("nope", first))
        self.assertFalse(auth.verify_password("secret", None))

    def test_bootstrap_admin_can_authenticate(self):
        user = auth.authenticate("mis@adonisgroup.in", "ADONIS@13719")
        self.assertIsNotNone(user)
        self.assertEqual(user["role"], "ADMIN")
        self.assertNotIn("password_hash", user)

    def test_email_is_case_insensitive(self):
        self.assertIsNotNone(auth.authenticate("MIS@AdonisGroup.in", "ADONIS@13719"))

    def test_wrong_password_and_unknown_user_rejected(self):
        self.assertIsNone(auth.authenticate("mis@adonisgroup.in", "wrong"))
        self.assertIsNone(auth.authenticate("nobody@company.com", "ADONIS@13719"))

    def test_deactivated_user_cannot_authenticate(self):
        user = auth.authenticate("mis@adonisgroup.in", "ADONIS@13719")
        auth.update_user_status(user["id"], False)
        self.assertIsNone(auth.authenticate("mis@adonisgroup.in", "ADONIS@13719"))

    def test_add_user_with_password_never_leaks_hash(self):
        created = auth.add_user("analyst@company.com", "USER", "pw123456")
        self.assertNotIn("password_hash", created)
        self.assertIsNotNone(auth.authenticate("analyst@company.com", "pw123456"))
        for row in auth.get_all_users():
            self.assertNotIn("password_hash", row)


if __name__ == "__main__":
    unittest.main()
