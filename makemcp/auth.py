"""Auth helpers (static tokens, simple validator)."""
from __future__ import annotations
from .exceptions import AuthError


def require_token(provided: str | None, expected: str | None):
    if expected and provided != expected:
        raise AuthError("Unauthorized")
