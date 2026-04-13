"""
Clerk authentication — verify JWTs from Clerk's frontend SDK.

Clerk handles sign-up/sign-in UI (email, Google, Apple) on the frontend.
This module verifies the session token on the backend using Clerk's JWKS.
"""

import os
import logging
import base64
from typing import Optional, Dict
from functools import lru_cache

import jwt
import httpx

logger = logging.getLogger(__name__)

# Lazy-loaded config (env vars may not be set at import time)
_config = {}


def _ensure_config():
    """Load Clerk config from env vars on first use."""
    if _config:
        return
    _config["pk"] = os.getenv("CLERK_PUBLISHABLE_KEY", "")
    _config["sk"] = os.getenv("CLERK_SECRET_KEY", "")
    _config["frontend_api"] = ""
    pk = _config["pk"]
    if pk:
        try:
            prefix = pk.split("_", 2)[-1]
            padded = prefix + "=" * (4 - len(prefix) % 4) if len(prefix) % 4 else prefix
            _config["frontend_api"] = base64.b64decode(padded).decode().rstrip("$")
            logger.info(f"Clerk frontend API: {_config['frontend_api']}")
        except Exception as e:
            logger.warning(f"Could not parse Clerk publishable key: {e}")


def is_clerk_enabled() -> bool:
    """Check if Clerk is configured."""
    _ensure_config()
    return bool(_config.get("pk") and _config.get("sk"))


def get_publishable_key() -> str:
    _ensure_config()
    return _config.get("pk", "")


@lru_cache(maxsize=1)
def _get_jwks():
    """Fetch Clerk's JWKS (cached)."""
    _ensure_config()
    sk = _config.get("sk", "")
    frontend_api = _config.get("frontend_api", "")
    if sk:
        r = httpx.get(
            "https://api.clerk.com/v1/jwks",
            headers={"Authorization": f"Bearer {sk}"},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    elif frontend_api:
        r = httpx.get(f"https://{frontend_api}/.well-known/jwks.json", timeout=10)
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
    """
    if not token:
        return None
    try:
        public_key = _get_public_key()
        if not public_key:
            logger.warning("No Clerk public key available")
            return None
        return jwt.decode(
            token, public_key, algorithms=["RS256"],
            options={"verify_exp": True, "verify_iat": True, "verify_nbf": True},
        )
    except jwt.ExpiredSignatureError:
        logger.debug("Clerk token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.debug(f"Invalid Clerk token: {e}")
        return None


def get_clerk_user(user_id: str) -> Optional[Dict]:
    """Fetch user details from Clerk's Backend API."""
    _ensure_config()
    sk = _config.get("sk", "")
    if not sk:
        return None
    try:
        r = httpx.get(
            f"https://api.clerk.com/v1/users/{user_id}",
            headers={"Authorization": f"Bearer {sk}"},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
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
