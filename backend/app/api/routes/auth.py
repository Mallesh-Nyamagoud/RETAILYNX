import os
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth
from itsdangerous import URLSafeSerializer

from app.services.auth import get_user_by_email, get_user_by_id, get_all_users, add_user, update_user_status, remove_user, authenticate
from app.models.auth import LoginRequest, UserCreate, UserUpdate

router = APIRouter(prefix="/auth", tags=["auth"])

# --- Setup OAuth ---
oauth = OAuth()
oauth.register(
    name='google',
    client_id=os.environ.get("GOOGLE_CLIENT_ID", "dummy-dev-client-id"),
    client_secret=os.environ.get("GOOGLE_CLIENT_SECRET", "dummy-dev-client-secret"),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile',
        'prompt': 'select_account'
    }
)

# Initialize Session serializer for tamper-proof cookies
SECRET_KEY = os.environ.get("AUTH_SECRET_KEY", "dev-secret-key-replace-in-prod")
serializer = URLSafeSerializer(SECRET_KEY)

COOKIE_NAME = "retailynx_session"


# --- Dependencies ---

def get_current_user(request: Request):
    """Validates the session cookie and returns the active user."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        user_id = serializer.loads(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid session")
        
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
        
    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="Your account is deactivated.")
        
    return user


def get_current_admin(user = Depends(get_current_user)):
    """Ensures the user is an admin."""
    if user["role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# --- OAuth Routes ---

@router.get("/login")
async def login(request: Request):
    """Initiates Google OAuth flow."""
    redirect_uri = os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/auth/callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/callback")
async def callback(request: Request):
    """Handles the callback from Google."""
    try:
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get('userinfo')
        if not user_info:
            raise Exception("No user info found")
    except Exception as e:
        return RedirectResponse(url="/login?error=oauth_failed")

    email = user_info.get("email", "").lower()
    user = get_user_by_email(email)
    
    if not user:
        return RedirectResponse(url="/login?error=unauthorized_email")
        
    if not user["is_active"]:
        return RedirectResponse(url="/login?error=deactivated")

    # Success: issue tamper-proof cookie
    session_token = serializer.dumps(user["id"])
    
    response = RedirectResponse(url="/")
    response.set_cookie(
        key=COOKIE_NAME,
        value=session_token,
        httponly=True,
        secure=os.environ.get("ENVIRONMENT") == "production",
        samesite="lax",
        max_age=86400 * 7 # 7 days
    )
    return response


@router.post("/login")
async def password_login(data: LoginRequest, response: Response):
    """Email + password login (used instead of Google sign-in).

    On success it issues the SAME signed session cookie the Google flow uses,
    so every protected route (get_current_user) keeps working unchanged.
    """
    user = authenticate(data.email, data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    session_token = serializer.dumps(user["id"])
    response.set_cookie(
        key=COOKIE_NAME,
        value=session_token,
        httponly=True,
        secure=os.environ.get("ENVIRONMENT") == "production",
        samesite="lax",
        max_age=86400 * 7,  # 7 days
    )
    return user


@router.post("/logout")
async def logout(response: Response):
    """Clears the session."""
    response.delete_cookie(COOKIE_NAME)
    return {"status": "ok"}


@router.get("/me")
async def get_me(user = Depends(get_current_user)):
    """Returns the currently authenticated user."""
    return user


# --- Admin User Management Routes ---

@router.get("/users")
def list_users(admin = Depends(get_current_admin)):
    return get_all_users()


@router.post("/users")
def create_user(data: UserCreate, admin = Depends(get_current_admin)):
    try:
        return add_user(data.email, data.role, data.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/users/{user_id}")
def update_user(user_id: int, data: UserUpdate, admin = Depends(get_current_admin)):
    update_user_status(user_id, data.is_active)
    return {"status": "ok"}


@router.delete("/users/{user_id}")
def delete_user(user_id: int, admin = Depends(get_current_admin)):
    # Prevent deleting oneself
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="Cannot remove your own account")
    remove_user(user_id)
    return {"status": "ok"}
