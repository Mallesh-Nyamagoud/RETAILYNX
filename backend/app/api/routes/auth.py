"""Authentication routes: username + password login with signed session cookies.

There is no Google/OAuth flow any more. The session is a signed (itsdangerous)
cookie holding only the user id, which is re-checked against the database on
every protected request - so disabling or deleting a user takes effect
immediately, without waiting for the cookie to expire.

Cookie flags:
    HttpOnly     - JavaScript can never read the session token (XSS defence)
    Secure       - only sent over HTTPS (enabled automatically in production)
    SameSite=Lax - not sent on cross-site POSTs (CSRF defence), while still
                   surviving a normal top-level navigation into the app
"""
from __future__ import annotations

from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from itsdangerous import BadSignature, URLSafeSerializer

from app.core.config import (
    GOOGLE_OAUTH_CLIENT_ID,
    GOOGLE_WORKSPACE_DOMAIN,
    IS_PRODUCTION,
    SESSION_SECRET_KEY,
)
from app.models.auth import GoogleLoginRequest, LoginRequest, UserCreate, UserUpdate
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

COOKIE_NAME = "retailynx_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 12  # 12 hours

# Signing key for the session cookie. validate_startup_config() guarantees this
# is present (and, in production, not the public placeholder) before we serve.
serializer = URLSafeSerializer(SESSION_SECRET_KEY or "unsafe-dev-only-key")


def _set_session_cookie(response: Response, user_id: int, session_id: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=serializer.dumps({"user_id": user_id, "session_id": session_id}),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=IS_PRODUCTION,
        samesite="lax",
        path="/",
    )


# --- Dependencies ----------------------------------------------------------
def get_current_user(request: Request) -> dict:
    """Resolve the signed session cookie to an active user, else 401."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = serializer.loads(token)
        user_id = payload.get("user_id") if isinstance(payload, dict) else payload
        session_id = payload.get("session_id") if isinstance(payload, dict) else None
    except BadSignature:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid session")

    user = auth_service.get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="User no longer exists")
    if not user["is_active"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Your account has been disabled")
    if session_id:
        auth_service.record_interaction(session_id)
    return user


CurrentUser = Annotated[dict, Depends(get_current_user)]


def get_current_admin(user: CurrentUser) -> dict:
    """Admin-only guard for the "User Access" endpoints."""
    if user["role"] != "ADMIN":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


CurrentAdmin = Annotated[dict, Depends(get_current_admin)]


# --- Session --------------------------------------------------------------
@router.get("/google/config")
def google_login_config() -> dict:
    """Public client settings for the Google Identity Services button."""
    return {"client_id": GOOGLE_OAUTH_CLIENT_ID, "domain": GOOGLE_WORKSPACE_DOMAIN}


@router.post("/google/login")
def google_login(payload: GoogleLoginRequest, response: Response) -> dict:
    """Verify a Google Workspace ID token and issue the normal app session."""
    if not GOOGLE_OAUTH_CLIENT_ID:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="Google sign-in is not configured")

    try:
        from google.auth.transport.requests import Request as GoogleRequest
        from google.oauth2 import id_token
    except ImportError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="Google sign-in verification is unavailable") from None

    try:
        identity = id_token.verify_oauth2_token(
            payload.credential, GoogleRequest(), GOOGLE_OAUTH_CLIENT_ID
        )
    except Exception:
        # Do not include or log the submitted bearer token.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Google sign-in could not be verified")

    email = str(identity.get("email") or "").strip().lower()
    hosted_domain = str(identity.get("hd") or "").strip().lower()
    google_sub = str(identity.get("sub") or "").strip()
    issuer = identity.get("iss")
    if issuer not in {"accounts.google.com", "https://accounts.google.com"}:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Google sign-in could not be verified")
    if identity.get("email_verified") is not True or not google_sub or not email:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Use a verified company Google account")
    if hosted_domain != GOOGLE_WORKSPACE_DOMAIN or email.rsplit("@", 1)[-1] != GOOGLE_WORKSPACE_DOMAIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=f"Only {GOOGLE_WORKSPACE_DOMAIN} accounts can sign in")

    user = auth_service.get_user_by_google_sub(google_sub)
    if user is None:
        # Workspace verified email is authoritative; link a pre-existing local
        # account by email so its role and permissions remain intact.
        user = auth_service.get_user_by_username(email)
        if user is None:
            try:
                user = auth_service.add_user(email, "USER", google_sub=google_sub)
            except ValueError:
                user = auth_service.get_user_by_username(email)
        if user is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Could not create the application account")
        if not user.get("google_sub"):
            try:
                auth_service.link_google_sub(user["id"], google_sub)
            except Exception:
                # A concurrent Google login may have linked this subject first.
                user = auth_service.get_user_by_google_sub(google_sub) or user

    if not user["is_active"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Your account has been disabled")

    session_id = uuid.uuid4().hex
    auth_service.start_usage_session(session_id, user, auth_method="google", google_email=email)
    _set_session_cookie(response, user["id"], session_id)
    return user


@router.post("/login")
def login(payload: LoginRequest, response: Response) -> dict:
    """Verify credentials and issue the signed session cookie."""
    user = auth_service.authenticate(payload.username, payload.password)
    if user is None:
        # One message for every failure mode (unknown user, wrong password,
        # disabled account, lockout) so the response cannot be used to probe
        # which usernames exist.
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password"
        )
    session_id = uuid.uuid4().hex
    auth_service.start_usage_session(session_id, user, auth_method="password")
    _set_session_cookie(response, user["id"], session_id)
    return user


@router.post("/admin-login")
def admin_login(payload: LoginRequest, response: Response) -> dict:
    """Sign in only an ADMIN account from the account menu's admin gate."""
    user = auth_service.authenticate(payload.username, payload.password)
    if user is None or user["role"] != "ADMIN":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Invalid admin username or password")
    session_id = uuid.uuid4().hex
    auth_service.start_usage_session(session_id, user, auth_method="password")
    _set_session_cookie(response, user["id"], session_id)
    return user

@router.post("/logout")
def logout(request: Request, response: Response) -> dict:
    """Record logout and clear the session cookie."""
    token = request.cookies.get(COOKIE_NAME)
    if token:
        try:
            payload = serializer.loads(token)
            if isinstance(payload, dict) and payload.get("session_id"):
                auth_service.end_usage_session(payload["session_id"])
        except BadSignature:
            pass
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"status": "ok"}


@router.get("/me")
def read_current_user(user: CurrentUser) -> dict:
    """The currently signed-in user (used by the SPA on every page load)."""
    return user


# --- Admin: User Access ---------------------------------------------------
@router.get("/admin/overview")
def admin_overview(admin: CurrentAdmin) -> dict:
    from app.core.database import execute

    def latest_by_brand(schema: str, date_column: str, source_name_column: str) -> list[dict]:
        from app.core.database import column_exists

        if not column_exists(schema, "data", source_name_column):
            return []
        try:
            rows = execute(
                f"WITH brand_names AS ("
                f"SELECT CAST(brand_code AS VARCHAR) AS brand_code, "
                f"MIN(NULLIF(TRIM(brand), '')) AS brand_name "
                f"FROM store_master.store_details GROUP BY brand_code) "
                f"SELECT COALESCE(bn.brand_name, "
                f"NULLIF(TRIM(CAST(d.{source_name_column} AS VARCHAR)), '')) AS brand_name, "
                f"MAX(d.{date_column}) AS max_date "
                f"FROM {schema}.data d LEFT JOIN brand_names bn "
                f"ON CAST(d.brand_code AS VARCHAR) = bn.brand_code "
                f"WHERE d.{source_name_column} IS NOT NULL "
                f"AND (bn.brand_name IS NOT NULL OR "
                f"TRY_CAST(NULLIF(TRIM(CAST(d.{source_name_column} AS VARCHAR)), '') AS BIGINT) IS NULL) "
                f"GROUP BY 1 ORDER BY 1"
            )
        except Exception:
            return []
        return [
            {
                "brand_name": str(brand_name),
                "max_date": value.isoformat() if hasattr(value, "isoformat") else str(value) if value is not None else None,
            }
            for brand_name, value in rows
        ]

    return {
        "sessions": auth_service.get_usage_sessions(),
        "tertiary": latest_by_brand("tertiary_data", "date", "brand"),
        "secondary": latest_by_brand("secondary_data", "bill_date", "brand_desc"),
    }

@router.get("/users")
def list_users(admin: CurrentAdmin) -> list[dict]:
    return auth_service.get_all_users()


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, admin: CurrentAdmin) -> dict:
    try:
        return auth_service.add_user(payload.username, payload.role, payload.password)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.put("/users/{user_id}")
def update_user(user_id: int, payload: UserUpdate, admin: CurrentAdmin) -> dict:
    """Set/reset a password, change a role and/or enable-disable an account.

    Guard rails: an admin cannot lock *themselves* out (demote or disable their
    own account), and the last remaining admin can never be demoted or
    disabled - otherwise nobody could manage users any more.
    """
    target = auth_service.get_user_by_id(user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")

    is_self = target["id"] == admin["id"]
    if is_self and payload.role is not None and payload.role != target["role"]:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="You cannot change your own role"
        )
    if is_self and payload.is_active is False:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="You cannot disable your own account"
        )

    demoting = payload.role is not None and payload.role != "ADMIN" and target["role"] == "ADMIN"
    disabling = payload.is_active is False and target["role"] == "ADMIN"
    if (demoting or disabling) and auth_service.count_admins(exclude_id=target["id"]) == 0:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="At least one ADMIN account must remain"
        )

    try:
        if payload.role is not None:
            auth_service.update_user_role(user_id, payload.role)
        if payload.is_active is not None:
            auth_service.update_user_status(user_id, payload.is_active)
        if payload.password:
            auth_service.set_password(user_id, payload.password)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return auth_service.get_user_by_id(user_id) or {"status": "ok"}


@router.delete("/users/{user_id}")
def delete_user(user_id: int, admin: CurrentAdmin) -> dict:
    target = auth_service.get_user_by_id(user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")
    if target["id"] == admin["id"]:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="You cannot remove your own account"
        )
    if target["role"] == "ADMIN" and auth_service.count_admins(exclude_id=target["id"]) == 0:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="At least one ADMIN account must remain"
        )
    auth_service.remove_user(user_id)
    return {"status": "ok"}