import hashlib
import hmac
import secrets


def generate_token() -> str:
    """A raw, unguessable token — this is what goes in the cookie and is
    never persisted. Only its hash (see hash_token) is stored server-side.
    """
    return secrets.token_urlsafe(32)


def hash_token(token: str, secret: str) -> str:
    """HMAC-SHA256 keyed by SESSION_SECRET, not a bare hash. The token
    already has 256 bits of entropy, so this isn't protecting against
    brute-forcing the hash — it's what gives SESSION_SECRET a real
    purpose: rotating it invalidates every stored session at once (every
    hash_token comparison starts failing), a deliberate emergency
    "revoke all sessions" lever.
    """
    return hmac.new(secret.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()
