from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()  # argon2id with library-recommended parameters
# Verified against when the user doesn't exist, so response time doesn't reveal that.
_DUMMY_HASH = _hasher.hash("not-a-real-password")

MIN_LENGTH = 8


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def is_acceptable(password: str) -> bool:
    return len(password) >= MIN_LENGTH and not password.isdigit()
