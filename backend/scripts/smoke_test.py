"""Local end-to-end smoke test: boot the real server and hit it over HTTP.

Mirrors what the container does on Cloud Run (real HTTP requests through the
same FastAPI app), so the same code path is exercised locally. Run from
`backend/`:

    python scripts/smoke_test.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PORT = "8123"
BASE = f"http://127.0.0.1:{PORT}"

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "local-dev-password"


def call(method: str, path: str, body=None, cookie: str | None = None):
    """Return (status, json-or-text, set-cookie header or None)."""
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", **({"Cookie": cookie} if cookie else {})},
    )
    try:
        with urllib.request.urlopen(request) as response:
            raw = response.read().decode()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = raw
            return response.status, payload, response.headers.get("Set-Cookie")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = raw
        return exc.code, payload, exc.headers.get("Set-Cookie")


def report(status, expected, method, path, extra=""):
    ok = status == expected
    print(f"[{'ok  ' if ok else 'FAIL'}] {method:<4} {path:<22} -> {status} {extra}".rstrip())
    return ok


def main() -> int:
    db_path = BACKEND_DIR / "data" / "smoke_auth.db"
    db_path.unlink(missing_ok=True)
    env = {
        **os.environ,
        "SESSION_SECRET_KEY": "local-smoke-test-secret-key-0123456789",
        "ADMIN_USERNAME": ADMIN_USERNAME,
        "ADMIN_PASSWORD": ADMIN_PASSWORD,
        "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
        "BCRYPT_ROUNDS": "4",
        "PYTHONPATH": str(BACKEND_DIR),
    }

    print(f"Starting uvicorn on port {PORT} ...")
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", PORT],
        cwd=str(BACKEND_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    failures: list[str] = []
    try:
        for _ in range(240):
            if process.poll() is not None:
                print(process.stdout.read() if process.stdout else "")
                failures.append("server exited before becoming healthy")
                return _finish(process, failures)
            try:
                status, payload, _ = call("GET", "/health")
                if status == 200:
                    report(status, 200, "GET", "/health", payload)
                    break
            except (urllib.error.URLError, ConnectionError):
                pass
            time.sleep(0.5)
        else:
            failures.append("server never became healthy")
            return _finish(process, failures)

        _check_routes(failures)
        _check_session(failures, process)
    finally:
        code = _finish(process, failures)
    return code


def _check_routes(failures: list[str]) -> None:
    """Public vs protected routes, and the generic failure message."""
    for method, path, body, expected in [
        ("GET", "/api/health", None, 200),
        ("GET", "/api/auth/me", None, 401),
        ("GET", "/api/meta/databases", None, 401),
        ("GET", "/api/auth/users", None, 401),
        ("POST", "/api/auth/login", {"username": ADMIN_USERNAME, "password": "wrong"}, 401),
        ("POST", "/api/auth/login", {"username": "ghost", "password": "whatever"}, 401),
    ]:
        status, _, _ = call(method, path, body)
        if not report(status, expected, method, path):
            failures.append(f"{method} {path}: expected {expected}, got {status}")


def _check_session(failures: list[str], process: subprocess.Popen) -> None:
    """Real login -> cookie flags -> authenticated calls -> logout."""
    status, payload, set_cookie = call(
        "POST", "/api/auth/login", {"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD}
    )
    if not report(status, 200, "POST", "/api/auth/login", payload):
        failures.append(f"login failed: {status} {payload}")
        return

    cookie = (set_cookie or "").split(";")[0]
    for flag in ("httponly", "samesite=lax"):
        present = flag in (set_cookie or "").lower()
        report(200 if present else 0, 200, "cookie", flag)
        if not present:
            failures.append(f"cookie is missing {flag}")
    if "secure" in (set_cookie or "").lower():
        failures.append("cookie is Secure in development (plain-http login would break)")
        report(0, 200, "cookie", "Secure-absent")

    for method, path, expected in [
        ("GET", "/api/auth/me", 200),
        ("GET", "/api/meta/databases", 200),
    ]:
        status, payload, _ = call(method, path, cookie=cookie)
        if not report(status, expected, method, path, payload):
            failures.append(f"{method} {path} with a session returned {status}")

    status, _, _ = call("POST", "/api/auth/logout", cookie=cookie)
    if not report(status, 200, "POST", "/api/auth/logout"):
        failures.append(f"logout returned {status}")

    # The server session is stateless: the cookie is *expired client-side* by
    # logout (Max-Age=0). Prove the server side really validates the signature
    # by pushing a forged token.
    status, _, _ = call("GET", "/api/auth/me", cookie="retailynx_session=tampered.invalid")
    if not report(status, 401, "GET", "/api/auth/me", "(forged cookie)"):
        failures.append(f"a forged cookie was accepted: {status}")


def _finish(process: subprocess.Popen, failures: list[str]) -> int:
    process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
    # Windows keeps the SQLite file locked until the engine is fully released.
    time.sleep(1.0)
    for suffix in ("", "-journal", "-wal", "-shm"):
        (BACKEND_DIR / "data" / f"smoke_auth.db{suffix}").unlink(missing_ok=True)
    print()
    if failures:
        print(f"SMOKE TEST FAILED ({len(failures)}):")
        for failure in failures:
            print("  -", failure)
        return 1
    print("SMOKE TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())