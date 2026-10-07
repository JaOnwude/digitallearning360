"""Small, audited crypto helpers. Never roll anything cleverer than this by hand."""

import base64
import hashlib
import hmac
import os
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings


def _key() -> bytes:
    raw = base64.urlsafe_b64decode(get_settings().encryption_key.get_secret_value())
    if len(raw) != 32:
        raise ValueError("DL360_ENCRYPTION_KEY must decode to 32 bytes")
    return raw


def encrypt(plaintext: str) -> str:
    """AES-256-GCM. Output: base64url(nonce || ciphertext+tag)."""
    nonce = os.urandom(12)
    ct = AESGCM(_key()).encrypt(nonce, plaintext.encode(), None)
    return base64.urlsafe_b64encode(nonce + ct).decode()


def decrypt(token: str) -> str:
    data = base64.urlsafe_b64decode(token)
    return AESGCM(_key()).decrypt(data[:12], data[12:], None).decode()


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())
