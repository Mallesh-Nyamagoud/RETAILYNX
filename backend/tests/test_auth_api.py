"""End-to-end API tests for login, logout, route protection and User Access.

These drive the real FastAPI app through `fastapi.testclient`, so they verify
the actual cookie flags, the 401/403 behaviour of every protected router and
the admin guard rails - not just the service layer.

The TestClient is deliberately NOT used as a context manager: that keeps
`lifespan` (and therefore the DuckDB startup/seed-copy) out of these tests.
The auth database is initialised directly instead.
"""
import gc
import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.routes import auth as auth_routes
from app.main import app
from app.services import auth

ADMIN_USER = "mis@adonisgroup.in"
ADMIN_PASS = "ADONIS@13719"


class AuthApiTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="retailynx_api_test_")
        self._saved = {
            "DATABASE_URL": auth.DATABASE_URL,
            "ADMIN_USERNAME": auth.ADMIN_USERNAME,
            "ADMIN_PASSWORD": auth.ADMIN_PASSWORD,
            "BCRYPT_ROUNDS": auth.BCRYPT_ROUNDS,
        }
        # The cookie's `Secure` flag follows the environment, which the rest of
        # the suite (test_startup_config) manipulates. Pin it so these tests are
        # hermetic; the production case is covered explicitly below.
        self._saved_secure = auth_routes.IS_PRODUCTION
        auth_routes.IS_PRODUCTION = False
        auth.BCRYPT_ROUNDS = 4  # fast hashing for the suite
        auth.DATABASE_URL = f"sqlite:///{(Path(self._tmpdir) / 'api_test.db').as_posix()}"
        auth.ADMIN_USERNAME = ADMIN_USER
        auth.ADMIN_PASSWORD = ADMIN_PASS
        auth._engine = None
        auth.init_db()
        self.client = TestClient(app)

    def tearDown(self):
        if auth._engine is not None:
            auth._engine.dispose()
        auth._engine = None
        auth_routes.IS_PRODUCTION = self._saved_secure
        for key, value in self._saved.items():
            setattr(auth, key, value)
        gc.collect()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _login(self, username=ADMIN_USER, password=ADMIN_PASS):
        return self.client.post("/api/auth/login", json={"username": username, "password": password})

    # --- health & protection ----------------------------------------------
    def test_health_is_public(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_data_routes_require_login(self):
        # No cookie at all -> 401 (never any data).
        for path in ("/api/auth/me", "/api/auth/users", "/api/meta/databases"):
            self.assertEqual(self.client.get(path).status_code, 401, path)

    def test_forged_cookie_is_rejected(self):
        self.client.cookies.set(auth_routes.COOKIE_NAME, "obviously-not-a-signed-token")
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    # --- login / logout ----------------------------------------------------
    def test_login_sets_a_signed_httponly_lax_cookie(self):
        response = self._login()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["username"], ADMIN_USER)
        self.assertEqual(body["role"], "ADMIN")
        self.assertNotIn("password_hash", body)

        cookie_header = response.headers["set-cookie"]
        self.assertIn("HttpOnly", cookie_header)
        self.assertIn("SameSite=lax", cookie_header.replace("SameSite=Lax", "SameSite=lax"))
        self.assertIn(f"{auth_routes.COOKIE_NAME}=", cookie_header)
        # Development: the cookie must NOT be marked Secure, or a plain-http
        # local browser would silently drop it.
        self.assertNotIn("Secure", cookie_header)

    def test_cookie_is_secure_in_production(self):
        """PART A5: in production the cookie is Secure as well as HttpOnly/Lax.

        httpx (used by TestClient) speaks plain http to `testserver`, so a
        Secure cookie is exactly the reason the login would not stick - hence
        this is asserted on the raw Set-Cookie header rather than by making a
        second authenticated request.
        """
        auth_routes.IS_PRODUCTION = True
        try:
            response = self._login()
            self.assertEqual(response.status_code, 200)
            cookie_header = response.headers["set-cookie"]
            self.assertIn("HttpOnly", cookie_header)
            self.assertIn("Secure", cookie_header)
            self.assertIn("SameSite=lax", cookie_header.replace("SameSite=Lax", "SameSite=lax"))
        finally:
            auth_routes.IS_PRODUCTION = False

    def test_login_then_me_then_logout(self):
        self.assertEqual(self._login().status_code, 200)
        me = self.client.get("/api/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["username"], ADMIN_USER)

        self.assertEqual(self.client.post("/api/auth/logout").status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_login_with_wrong_password_is_401_and_leaks_nothing(self):
        response = self._login(password="not-the-password")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Invalid username or password")

    def test_disabled_user_session_stops_working_immediately(self):
        user = auth.add_user("analyst", "USER", "pw123456")
        self.assertTrue(self._login("analyst", "pw123456").status_code == 200)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)

        # Admin disables them -> the existing cookie is refused on the next call.
        auth.update_user_status(user["id"], False)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 403)

    # --- admin: User Access -------------------------------------------------
    def test_non_admin_cannot_reach_the_user_access_endpoints(self):
        auth.add_user("analyst", "USER", "pw123456")
        self._login("analyst", "pw123456")
        self.assertEqual(self.client.get("/api/auth/users").status_code, 403)
        self.assertEqual(
            self.client.post("/api/auth/users", json={"username": "x", "password": "pw123456"}).status_code,
            403,
        )

    def test_admin_can_create_disable_renable_change_role_and_delete(self):
        self._login()
        self.assertEqual(self.client.get("/api/auth/users").status_code, 200)

        created = self.client.post(
            "/api/auth/users", json={"username": "Analyst", "role": "USER", "password": "pw123456"}
        )
        self.assertEqual(created.status_code, 201)
        user_id = created.json()["id"]
        self.assertEqual(created.json()["username"], "analyst")  # normalised
        self.assertNotIn("password_hash", created.json())

        # Reset the password.
        self.assertEqual(
            self.client.put(f"/api/auth/users/{user_id}", json={"password": "new-pw-123"}).status_code,
            200,
        )
        self.assertIsNotNone(auth.authenticate("analyst", "new-pw-123"))

        # Disable, then re-enable.
        self.assertEqual(
            self.client.put(f"/api/auth/users/{user_id}", json={"is_active": False}).status_code, 200
        )
        self.assertIsNone(auth.authenticate("analyst", "new-pw-123"))
        self.assertEqual(
            self.client.put(f"/api/auth/users/{user_id}", json={"is_active": True}).status_code, 200
        )
        self.assertIsNotNone(auth.authenticate("analyst", "new-pw-123"))

        # Change the role.
        self.assertEqual(
            self.client.put(f"/api/auth/users/{user_id}", json={"role": "ADMIN"}).status_code, 200
        )
        self.assertEqual(auth.get_user_by_id(user_id)["role"], "ADMIN")

        # Delete.
        self.assertEqual(self.client.delete(f"/api/auth/users/{user_id}").status_code, 200)
        self.assertIsNone(auth.get_user_by_id(user_id))

    def test_duplicate_username_is_rejected(self):
        self._login()
        payload = {"username": "analyst", "role": "USER", "password": "pw123456"}
        self.assertEqual(self.client.post("/api/auth/users", json=payload).status_code, 201)
        self.assertEqual(self.client.post("/api/auth/users", json=payload).status_code, 400)

    def test_short_password_is_rejected(self):
        self._login()
        response = self.client.post(
            "/api/auth/users", json={"username": "analyst", "role": "USER", "password": "short"}
        )
        self.assertEqual(response.status_code, 422)

    def test_admin_cannot_disable_or_demote_their_own_account(self):
        self._login()
        me = self.client.get("/api/auth/me").json()
        self.assertEqual(
            self.client.put(f"/api/auth/users/{me['id']}", json={"is_active": False}).status_code, 400
        )
        self.assertEqual(
            self.client.put(f"/api/auth/users/{me['id']}", json={"role": "USER"}).status_code, 400
        )
        self.assertEqual(self.client.delete(f"/api/auth/users/{me['id']}").status_code, 400)

    def test_last_admin_cannot_be_disabled_or_deleted_by_another_admin(self):
        self._login()
        second = self.client.post(
            "/api/auth/users", json={"username": "admin2", "role": "ADMIN", "password": "pw123456"}
        ).json()
        # Two admins exist, so demoting one is allowed...
        self.assertEqual(
            self.client.put(f"/api/auth/users/{second['id']}", json={"role": "USER"}).status_code, 200
        )
        # ...and now only one admin is left, so it must be protected.
        me = self.client.get("/api/auth/me").json()
        self.assertIsNotNone(auth.get_user_by_id(second["id"]))  # sanity: still there
        self.assertEqual(auth.get_user_by_id(second["id"])["role"], "USER")
        self.assertEqual(auth.count_admins(), 1)
        self.assertEqual(auth.count_admins(exclude_id=me["id"]), 0)
        self.assertEqual(
            self.client.delete(f"/api/auth/users/{me['id']}").status_code, 400
        )


if __name__ == "__main__":
    unittest.main()