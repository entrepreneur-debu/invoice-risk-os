"""Security primitives: password hashing, opaque tokens, CSRF tokens, field encryption.

- Passwords: Argon2id (argon2-cffi defaults, RFC 9106 low-memory profile).
- Session/invitation tokens: 256-bit random, stored only as HMAC-SHA256(AUTH_SECRET).
- CSRF: double-submit token derived from the session, verified in constant time.
- Bank account numbers: AES-256-GCM with DATA_ENCRYPTION_KEY, plus a keyed fingerprint
  so values can be compared without decrypting.
"""

import base64
import contextlib
import hashlib
import hmac
import os
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.errors import InvalidInput

_password_hasher = PasswordHasher()

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128

# A precomputed hash so failed logins for unknown emails cost the same time.
_DUMMY_HASH = _password_hasher.hash("timing-equaliser-not-a-real-password")


def validate_password_policy(password: str, email: str | None = None) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise InvalidInput(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters", code="weak_password"
        )
    if len(password) > MAX_PASSWORD_LENGTH:
        raise InvalidInput("Password is too long", code="weak_password")
    if email and password.strip().lower() == email.strip().lower():
        raise InvalidInput("Password must not equal the email address", code="weak_password")
    if len(set(password)) < 5:
        raise InvalidInput("Password is too repetitive", code="weak_password")


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if password_hash is None:
        # Still spend the hashing time to avoid a user-enumeration timing oracle.
        with contextlib.suppress(VerificationError):
            _password_hasher.verify(_DUMMY_HASH, password)
        return False
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _password_hasher.check_needs_rehash(password_hash)


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str, secret: str) -> str:
    return hmac.new(secret.encode(), token.encode(), hashlib.sha256).hexdigest()


def csrf_token_for(session_token_hash: str, secret: str) -> str:
    return hmac.new(
        secret.encode(), f"csrf:{session_token_hash}".encode(), hashlib.sha256
    ).hexdigest()


def tokens_match(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


class FieldEncryptor:
    """AES-256-GCM for small sensitive fields. Ciphertext format: `v1:<base64(nonce|ct)>`."""

    _VERSION = "v1"

    def __init__(self, key: bytes) -> None:
        if len(key) != 32:
            raise ValueError("encryption key must be 32 bytes")
        self._aead = AESGCM(key)
        self._fingerprint_key = hmac.new(key, b"fingerprint", hashlib.sha256).digest()

    def encrypt(self, plaintext: str, associated_data: str) -> str:
        nonce = os.urandom(12)
        ciphertext = self._aead.encrypt(nonce, plaintext.encode(), associated_data.encode())
        return f"{self._VERSION}:{base64.b64encode(nonce + ciphertext).decode()}"

    def decrypt(self, token: str, associated_data: str) -> str:
        version, _, payload = token.partition(":")
        if version != self._VERSION:
            raise ValueError("unsupported ciphertext version")
        raw = base64.b64decode(payload)
        return self._aead.decrypt(raw[:12], raw[12:], associated_data.encode()).decode()

    def fingerprint(self, value: str) -> str:
        """Keyed, deterministic digest of a normalised value, for equality checks."""
        return hmac.new(self._fingerprint_key, value.encode(), hashlib.sha256).hexdigest()
