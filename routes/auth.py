import os
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow
from jose import JWTError, jwt

from database.supabase import get_supabase, has_supabase_config

router = APIRouter(prefix="", tags=["auth"])

# JWT configuration
JWT_SECRET = os.getenv("JWT_SECRET", "zarvio-secret-2026")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = int(os.getenv("JWT_EXPIRE_DAYS", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

# In-memory blacklist of revoked JWTs (jti -> expiry)
TOKEN_BLACKLIST: Dict[str, datetime] = {}


def _create_jwt_token(user_id: str, email: str) -> str:
    expires = datetime.utcnow() + timedelta(days=JWT_EXPIRE_DAYS)
    jti = str(uuid.uuid4())
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": expires,
        "jti": jti,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_jwt_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        # Remove expired blacklist entries
        now = datetime.utcnow()
        for k, exp in list(TOKEN_BLACKLIST.items()):
            if exp <= now:
                TOKEN_BLACKLIST.pop(k, None)

        jti = payload.get("jti")
        if jti and TOKEN_BLACKLIST.get(jti):
            raise JWTError("Token has been revoked")

        return payload
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))


def _get_or_create_user(email: str, name: Optional[str], picture: Optional[str], google_id: Optional[str]):
    if not has_supabase_config():
        raise RuntimeError("Missing Supabase configuration (SUPABASE_URL / SUPABASE_KEY).")

    supabase = get_supabase()

    def _fetch():
        return (
            supabase.table("users")
            .select("id, email, name, picture, google_id, plan")
            .eq("email", email)
            .limit(1)
            .execute()
        )

    result = _fetch()
    if getattr(result, "error", None):
        raise RuntimeError(f"Failed to fetch user: {result.error}")

    rows = getattr(result, "data", []) or []
    now = datetime.utcnow().isoformat()

    if rows:
        user = rows[0]
        try:
            supabase.table("users").update({"last_login": now}).eq("id", user.get("id")).execute()
        except Exception:
            pass
        return user

    # Create new user
    new_user = {
        "email": email,
        "name": name or "",
        "picture": picture or "",
        "google_id": google_id or "",
        "plan": "free",
        "created_at": now,
        "last_login": now,
    }

    try:
        create_result = supabase.table("users").insert(new_user).execute()
        if getattr(create_result, "error", None):
            raise RuntimeError(str(create_result.error))
        data = getattr(create_result, "data", []) or []
        return data[0] if data else new_user
    except Exception:
        return new_user


def _create_refresh_token(user_id: str) -> str:
    if not has_supabase_config():
        raise RuntimeError("Missing Supabase configuration (SUPABASE_URL / SUPABASE_KEY).")

    supabase = get_supabase()
    token = str(uuid.uuid4())
    expires = (datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)).isoformat()

    try:
        supabase.table("refresh_tokens").insert(
            {
                "user_id": user_id,
                "token": token,
                "expires_at": expires,
                "revoked": False,
            }
        ).execute()
    except Exception:
        pass

    return token


def _revoke_refresh_tokens(user_id: str):
    if not has_supabase_config():
        return

    supabase = get_supabase()
    try:
        supabase.table("refresh_tokens").update({"revoked": True}).eq("user_id", user_id).execute()
    except Exception:
        pass


def _validate_refresh_token(token: str) -> Optional[str]:
    if not has_supabase_config():
        return None

    supabase = get_supabase()

    def _fetch():
        return (
            supabase.table("refresh_tokens")
            .select("user_id, expires_at, revoked")
            .eq("token", token)
            .limit(1)
            .execute()
        )

    result = _fetch()
    if getattr(result, "error", None):
        return None

    rows = getattr(result, "data", []) or []
    if not rows:
        return None

    row = rows[0]
    if row.get("revoked"):
        return None

    expires_at = row.get("expires_at")
    if expires_at:
        try:
            exp_dt = datetime.fromisoformat(expires_at)
            if exp_dt < datetime.utcnow():
                return None
        except Exception:
            pass

    return str(row.get("user_id"))


@router.get("/auth/google")
async def google_oauth_url(request: Request):
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Google OAuth not configured")

    redirect_uri = str(request.url_for("google_callback")).replace("http://", "https://")

    from urllib.parse import urlencode
    params = urlencode({
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",
    })
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{params}"
    return RedirectResponse(url=auth_url)


@router.get("/auth/google/callback")
async def google_callback(request: Request):
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Google OAuth not configured")

    code = request.query_params.get("code")
    if not code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing code parameter")

    redirect_uri = str(request.url_for("google_callback")).replace("http://", "https://")

    import httpx as _httpx
    token_resp = _httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
    )
    if token_resp.status_code != 200:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to fetch token: {token_resp.text}")

    tokens = token_resp.json()
    id_token_str = tokens.get("id_token")
    if not id_token_str:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No id_token in response")

    idinfo = id_token.verify_oauth2_token(id_token_str, google_requests.Request(), GOOGLE_CLIENT_ID)

    email = idinfo.get("email")
    name = idinfo.get("name")
    picture = idinfo.get("picture")
    google_id = idinfo.get("sub")

    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unable to determine user email")

    user = _get_or_create_user(email=email, name=name, picture=picture, google_id=google_id)
    user_id = str(user.get("id") or email)
    token = _create_jwt_token(user_id=user_id, email=email)
    refresh_token = _create_refresh_token(user_id=user_id)

    redirect_url = (
        f"{FRONTEND_URL.rstrip('/')}" +
        f"/dashboard?token={token}&refresh={refresh_token}"
    )
    return RedirectResponse(url=redirect_url)


def _get_token_from_header(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1]


@router.get("/auth/me")
async def auth_me(authorization: Optional[str] = Header(None)):
    token = _get_token_from_header(authorization)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")

    payload = _decode_jwt_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    if not has_supabase_config():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Supabase not configured")

    supabase = get_supabase()
    res = supabase.table("users").select("*").eq("id", user_id).limit(1).execute()
    if getattr(res, "error", None):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(res.error))

    rows = getattr(res, "data", []) or []
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return rows[0]


@router.post("/auth/refresh")
async def auth_refresh(body: Dict[str, str]):
    refresh_token = body.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing refresh_token")

    user_id = _validate_refresh_token(refresh_token)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    # Rotate refresh token
    new_refresh_token = _create_refresh_token(user_id)

    # Optionally revoke old refresh token
    try:
        if has_supabase_config():
            supabase = get_supabase()
            supabase.table("refresh_tokens").update({"revoked": True}).eq("token", refresh_token).execute()
    except Exception:
        pass

    # Create new access token
    supabase = get_supabase() if has_supabase_config() else None
    email = None
    if supabase:
        res = supabase.table("users").select("email").eq("id", user_id).limit(1).execute()
        email = (getattr(res, "data", []) or [{}])[0].get("email")

    access_token = _create_jwt_token(user_id=user_id, email=email or "")
    return {"token": access_token, "refresh_token": new_refresh_token}


@router.post("/auth/logout")
async def auth_logout(authorization: Optional[str] = Header(None)):
    token = _get_token_from_header(authorization)
    if token:
        payload = None
        try:
            payload = _decode_jwt_token(token)
        except HTTPException:
            payload = None

        if payload:
            jti = payload.get("jti")
            exp = payload.get("exp")
            if jti and exp:
                try:
                    TOKEN_BLACKLIST[jti] = datetime.fromtimestamp(exp)
                except Exception:
                    pass

            # Revoke refresh tokens for this user
            user_id = payload.get("sub")
            if user_id:
                _revoke_refresh_tokens(user_id)

    return {"status": "logged out"}
