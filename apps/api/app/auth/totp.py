"""Authenticator-app codes for staff (R4)."""

import secrets

import pyotp
import segno

from app.core.crypto import sha256_hex

ISSUER = "DigitalLearning360"
RECOVERY_CODE_COUNT = 8


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning(secret: str, account: str) -> tuple[str, str]:
    """Return (otpauth URI, QR code as an SVG data URI)."""
    uri = pyotp.TOTP(secret).provisioning_uri(name=account, issuer_name=ISSUER)
    svg = segno.make(uri, error="m").svg_data_uri(scale=5, border=2)
    return uri, svg


def verify(secret: str, code: str) -> bool:
    code = code.strip().replace(" ", "")
    return code.isdigit() and pyotp.TOTP(secret).verify(code, valid_window=1)


def new_recovery_codes() -> tuple[list[str], list[str]]:
    """Return (codes to show once, hashes to store)."""
    codes = [f"{secrets.token_hex(2)}-{secrets.token_hex(2)}" for _ in range(RECOVERY_CODE_COUNT)]
    return codes, [sha256_hex(c) for c in codes]


def normalise_recovery_code(code: str) -> str:
    return code.strip().lower()
