"""
User authentication for Mentastic.

Provides password hashing (bcrypt), user CRUD, and JWT token handling.
"""

import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict

import bcrypt as _bcrypt

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Hash a password with bcrypt."""
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its bcrypt hash."""
    return _bcrypt.checkpw(password.encode(), password_hash.encode())


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------

_pool = None

def _get_pool():
    global _pool
    if _pool is None:
        from utils.db import DatabasePool
        _pool = DatabasePool()
    return _pool


def create_user(
    email: str,
    password: str,
    display_name: Optional[str] = None,
) -> Optional[Dict]:
    """Create a new user. Returns user dict or None if email already exists."""
    from sqlalchemy import text

    pw_hash = hash_password(password)
    pool = _get_pool()
    with pool.get_session() as session:
        result = session.execute(
            text("""
                INSERT INTO mentastic.users
                    (email, password_hash, display_name)
                VALUES
                    (:email, :pw_hash, :display_name)
                ON CONFLICT (email) DO NOTHING
                RETURNING user_id, email, display_name, is_admin, is_active, created_at
            """),
            {
                "email": email.lower().strip(),
                "pw_hash": pw_hash,
                "display_name": display_name or email.split("@")[0],
            },
        )
        row = result.fetchone()
        if not row:
            return None
        return _row_to_user(row, result.keys())


def get_user_by_email(email: str) -> Optional[Dict]:
    """Fetch a user by email address."""
    from sqlalchemy import text
    pool = _get_pool()
    with pool.get_session() as session:
        result = session.execute(
            text("""
                SELECT user_id, email, password_hash,
                       display_name, is_admin, is_active, created_at
                FROM mentastic.users
                WHERE email = :email AND is_active = TRUE
            """),
            {"email": email.lower().strip()},
        )
        row = result.fetchone()
        if not row:
            return None
        return _row_to_user(row, result.keys())


def get_user_by_id(user_id: str) -> Optional[Dict]:
    """Fetch a user by user_id (UUID)."""
    from sqlalchemy import text
    pool = _get_pool()
    with pool.get_session() as session:
        result = session.execute(
            text("""
                SELECT user_id, email, password_hash,
                       display_name, is_admin, is_active, created_at
                FROM mentastic.users
                WHERE user_id = :user_id AND is_active = TRUE
            """),
            {"user_id": user_id},
        )
        row = result.fetchone()
        if not row:
            return None
        return _row_to_user(row, result.keys())


def authenticate(email: str, password: str) -> Optional[Dict]:
    """Authenticate by email + password. Returns user dict on success, None on failure."""
    user = get_user_by_email(email)
    if not user:
        return None
    pw_hash = user.get("password_hash")
    if not pw_hash:
        return None
    if not verify_password(password, pw_hash):
        return None
    user.pop("password_hash", None)
    return user


def update_password(user_id: str, new_password: str) -> bool:
    """Update a user's password hash."""
    from sqlalchemy import text

    pw_hash = hash_password(new_password)
    pool = _get_pool()
    with pool.get_session() as session:
        result = session.execute(
            text("""
                UPDATE mentastic.users
                SET password_hash = :pw_hash, updated_at = :now
                WHERE user_id = :user_id AND is_active = TRUE
            """),
            {
                "pw_hash": pw_hash,
                "user_id": user_id,
                "now": datetime.now(timezone.utc),
            },
        )
        return result.rowcount > 0


def update_display_name(user_id: str, display_name: str) -> bool:
    """Update a user's display name."""
    from sqlalchemy import text

    pool = _get_pool()
    with pool.get_session() as session:
        result = session.execute(
            text("""
                UPDATE mentastic.users
                SET display_name = :display_name, updated_at = :now
                WHERE user_id = :user_id AND is_active = TRUE
            """),
            {
                "display_name": display_name.strip(),
                "user_id": user_id,
                "now": datetime.now(timezone.utc),
            },
        )
        return result.rowcount > 0


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

def create_jwt_token(user_id: str, email: str) -> str:
    """Create a JWT token for API authentication."""
    import jwt

    secret = os.getenv("JWT_SECRET", "mentastic-dev-secret")
    payload = {
        "user_id": str(user_id),
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_jwt_token(token: str) -> Optional[Dict]:
    """Decode and verify a JWT token. Returns payload dict or None."""
    import jwt

    secret = os.getenv("JWT_SECRET", "mentastic-dev-secret")
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        logger.debug("JWT expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.debug(f"Invalid JWT: {e}")
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_user(row, keys) -> Dict:
    """Convert a DB row to a user dict."""
    d = dict(zip(keys, row))
    if d.get("user_id"):
        d["user_id"] = str(d["user_id"])
    return d
