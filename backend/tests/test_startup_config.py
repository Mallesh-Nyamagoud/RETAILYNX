"""Startup configuration validation (PART B2).

The app must refuse to start - with a message that names the offending
variable - rather than booting half-configured and accepting logins it cannot
persist. These tests use `importlib.reload` so the module-level reads happen
under controlled environment values.
"""
import importlib
import os
import unittest
from unittest.mock import patch

from app.core import config

REQUIRED = ("SESSION_SECRET_KEY", "ADMIN_USERNAME", "ADMIN_PASSWORD", "DATABASE_URL", "DATA_DIR")


class StartupConfigTests(unittest.TestCase):
    def _reload(self, env: dict):
        """Reload app.core.config with exactly `env` set for the relevant vars."""
        clean = {name: None for name in REQUIRED}
        clean.update({name: None for name in ("ENVIRONMENT", "APP_DATA_DIR")})
        clean.update(env)
        return patch.dict(os.environ, {k: v for k, v in clean.items() if v is not None}, clear=False), clean

    def setUp(self):
        # `app.core.config` calls load_dotenv() at import time, which would
        # refill anything we clear from `backend/.env`. Disable it for the test.
        self._dotenv_patcher = patch("dotenv.load_dotenv", lambda *a, **k: None)
        self._dotenv_patcher.start()
        # Preserve and clear the vars these tests care about.
        self._saved = {name: os.environ.get(name) for name in REQUIRED + ("ENVIRONMENT",)}
        for name in REQUIRED + ("ENVIRONMENT",):
            os.environ.pop(name, None)

    def tearDown(self):
        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        self._dotenv_patcher.stop()
        importlib.reload(config)  # restore the real module state for other tests

    def _valid_env(self, **overrides):
        env = {
            "SESSION_SECRET_KEY": "a-long-enough-session-secret",
            "ADMIN_USERNAME": "admin",
            "ADMIN_PASSWORD": "a-strong-password",
        }
        env.update(overrides)
        for key, value in env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        return importlib.reload(config)

    # --- development --------------------------------------------------------
    def test_development_defaults_are_valid(self):
        module = self._valid_env(ENVIRONMENT=None)
        self.assertFalse(module.IS_PRODUCTION)
        module.validate_startup_config()  # must not raise
        # DATABASE_URL / DATA_DIR fall back to local defaults.
        self.assertTrue(module.DATABASE_URL.startswith("sqlite:///"))
        self.assertTrue(str(module.DATA_DIR).endswith("data"))

    def test_missing_secrets_are_reported_by_name(self):
        module = importlib.reload(config)  # nothing set at all
        self.assertEqual(
            sorted(module.missing_required_config()),
            ["ADMIN_PASSWORD", "ADMIN_USERNAME", "SESSION_SECRET_KEY"],
        )
        with self.assertRaises(RuntimeError) as ctx:
            module.validate_startup_config()
        message = str(ctx.exception)
        for name in ("SESSION_SECRET_KEY", "ADMIN_USERNAME", "ADMIN_PASSWORD"):
            self.assertIn(name, message)

    # --- production --------------------------------------------------------
    def test_production_requires_database_url_and_data_dir(self):
        module = self._valid_env(ENVIRONMENT="production")
        self.assertTrue(module.IS_PRODUCTION)
        self.assertEqual(sorted(module.missing_required_config()), ["DATABASE_URL", "DATA_DIR"])
        with self.assertRaises(RuntimeError):
            module.validate_startup_config()

    def test_production_accepts_a_fully_configured_environment(self):
        module = self._valid_env(
            ENVIRONMENT="production",
            DATABASE_URL="postgresql://u:p@host:5432/retailynx?sslmode=require",
            DATA_DIR="/app/backend/data",
        )
        module.validate_startup_config()  # must not raise
        self.assertEqual(module.missing_required_config(), [])

    def test_production_rejects_the_dev_placeholder_secret(self):
        module = self._valid_env(
            ENVIRONMENT="production",
            SESSION_SECRET_KEY="dev-secret-key-replace-in-prod",
            DATABASE_URL="postgresql://u:p@h/db",
            DATA_DIR="/app/backend/data",
        )
        with self.assertRaises(RuntimeError) as ctx:
            module.validate_startup_config()
        self.assertIn("placeholder", str(ctx.exception))

    def test_short_secret_and_password_are_rejected(self):
        module = self._valid_env(SESSION_SECRET_KEY="short", ADMIN_PASSWORD="tiny")
        with self.assertRaises(RuntimeError) as ctx:
            module.validate_startup_config()
        message = str(ctx.exception)
        self.assertIn("SESSION_SECRET_KEY", message)
        self.assertIn("ADMIN_PASSWORD", message)

    def test_blank_values_behave_like_unset_values(self):
        module = self._valid_env(SESSION_SECRET_KEY="   ", ADMIN_USERNAME="", ADMIN_PASSWORD=None)
        self.assertEqual(
            sorted(module.missing_required_config()),
            ["ADMIN_PASSWORD", "ADMIN_USERNAME", "SESSION_SECRET_KEY"],
        )

    def test_whitespace_is_trimmed_from_secrets(self):
        module = self._valid_env(SESSION_SECRET_KEY="  my-trimmed-secret-value  ")
        self.assertEqual(module.SESSION_SECRET_KEY, "my-trimmed-secret-value")


if __name__ == "__main__":
    unittest.main()