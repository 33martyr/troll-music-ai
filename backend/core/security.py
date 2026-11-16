"""API-key access control.

The studio is single-tenant: there are no user accounts. Setting
``TROLL_API_KEY`` puts every route behind that key. Media elements cannot send
headers, so file URLs carry a per-asset signature derived from the key instead
of the key itself.
"""

from __future__ import annotations

import hashlib
import hmac

from fastapi import Request

from backend.core.errors import ApiError

_secret: str | None = None


def configure(api_key: str | None) -> None:
    global _secret
    _secret = api_key or None


def file_token(resource_id: str) -> str | None:
    """Signature that grants read access to one file. ``None`` when auth is off."""
    if not _secret:
        return None
    return hmac.new(_secret.encode(), resource_id.encode(), hashlib.sha256).hexdigest()[:32]


def _bearer_ok(request: Request) -> bool:
    supplied = request.headers.get("authorization", "")
    return hmac.compare_digest(supplied, f"Bearer {_secret}")


def require_api_key(request: Request) -> None:
    if not _secret or request.method == "OPTIONS" or _bearer_ok(request):
        return
    # File routes also accept the signed token for that one resource.
    resource_id = request.path_params.get("file_id")
    token = request.query_params.get("token", "")
    if resource_id and hmac.compare_digest(token, file_token(resource_id) or ""):
        return
    raise ApiError(401, "unauthorized", "A valid API key is required.")
