"""
Clerk authentication — verify JWTs from Clerk's frontend SDK.

Clerk handles sign-up/sign-in UI (email, Google, Apple) on the frontend.
This module verifies the session token on the backend using Clerk's JWKS.
"""

import os
import logging
from typing import Optional, Dict
from functools import lru_cache

import jwt
import httpx

logger = logging.getLogger(__name__)

CLERK_SECRET_KEY = os.getenv("CLERK_SECRET_KEY", "")
CLERK_PUBLISHABLE_KEY = os.getenv("CLERK_PUBLISHABLE_KEY", "")
CLERK_FRONTEND_API = ""

# Extract frontend API URL from publishable key
# pk_test_xxx.clerk.accounts.dev → xxx.clerk.accounts.dev
if CLERK_PUBLISHABLE_KEY:
    import base64
    try:
        # The publishable key is pk_test_ or pk_live_ + base64(frontend_api)
        prefix = CLERK_PUBLISHABLE_KEY.split("_", 2)[-1]  # after pk_test_ or pk_live_
        # Remove trailing $ if present
        padded = prefix + "=" * (4 - len(prefix) % 4) if len(prefix) % 4 else prefix
        CLERK_FRONTEND_API = base64.b64decode(padded).decode().rstrip("$")
        logger.info(f"Clerk frontend API: {CLERK_FRONTEND_API}")
    except Exception as e:
        logger.warning(f"Could not parse Clerk publishable key: {e}")


@lru_cache(maxsize=1)
def _get_jwks():
    """Fetch Clerk's JWKS (cached)."""
    if CLERK_SECRET_KEY:
        # Use Backend API with secret key
        r = httpx.get(
            "https://api.clerk.com/v1/jwks",
            headers={"Authorization": f"Bearer {CLERK_SECRET_KEY}"},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    elif CLERK_FRONTEND_API:
        # Use Frontend API JWKS endpoint
        r = httpx.get(f"https://{CLERK_FRONTEND_API}/.well-known/jwks.json", timeout=10)
        r.raise_for_status()
        return r.json()
    return None


def _get_public_key():
    """Get the RSA public key from Clerk's JWKS."""
    jwks = _get_jwks()
    if not jwks or "keys" not in jwks:
        return None
    from jwt import PyJWK
    key_data = jwks["keys"][0]
    return PyJWK.from_dict(key_data).key


def verify_clerk_token(token: str) -> Optional[Dict]:
    """
    Verify a Clerk session JWT and return the decoded payload.
    Returns None if verification fails.

    The payload contains:
    - sub: Clerk user ID (e.g., "user_2abc...")
    - email: User's email (if available in session claims)
    - exp, iat, nbf: Timestamps
    """
    if not token:
        return None

    try:
        public_key = _get_public_key()
        if not public_key:
            logger.warning("No Clerk public key available")
            return None

        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            options={
                "verify_exp": True,
                "verify_iat": True,
                "verify_nbf": True,
            },
        )
        return payload
    except jwt.ExpiredSignatureError:
        logger.debug("Clerk token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.debug(f"Invalid Clerk token: {e}")
        return None


def get_clerk_user(user_id: str) -> Optional[Dict]:
    """Fetch user details from Clerk's Backend API."""
    if not CLERK_SECRET_KEY:
        return None
    try:
        r = httpx.get(
            f"https://api.clerk.com/v1/users/{user_id}",
            headers={"Authorization": f"Bearer {CLERK_SECRET_KEY}"},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        # Extract useful fields
        email = ""
        if data.get("email_addresses"):
            email = data["email_addresses"][0].get("email_address", "")
        return {
            "clerk_id": data.get("id"),
            "email": email,
            "first_name": data.get("first_name", ""),
            "last_name": data.get("last_name", ""),
            "display_name": f"{data.get('first_name', '')} {data.get('last_name', '')}".strip() or email.split("@")[0],
            "image_url": data.get("image_url", ""),
        }
    except Exception as e:
        logger.error(f"Failed to fetch Clerk user {user_id}: {e}")
        return None


def is_clerk_enabled() -> bool:
    """Check if Clerk is configured."""
    return bool(CLERK_PUBLISHABLE_KEY and CLERK_SECRET_KEY)
