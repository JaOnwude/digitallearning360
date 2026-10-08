"""Paystack: start a checkout, verify a transaction, check webhook signatures (R22).

Tests replace `get_paystack` with a fake (see tests/fees/fake_paystack.py); nothing here is
called over the network in the test suite.
"""

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from fastapi import HTTPException, status

from app.core.config import get_settings


@dataclass(frozen=True)
class Checkout:
    authorization_url: str
    reference: str


@dataclass(frozen=True)
class Verification:
    reference: str
    success: bool
    amount_kobo: int
    currency: str
    raw: dict[str, Any]


class PaystackClient(Protocol):
    async def initialize(
        self,
        *,
        email: str,
        amount_kobo: int,
        reference: str,
        callback_url: str,
        subaccount: str | None,
        metadata: dict[str, Any],
    ) -> Checkout: ...

    async def verify(self, reference: str) -> Verification: ...


UNAVAILABLE = "Online payment is temporarily unavailable. Please try again or pay by bank transfer."


class PaystackUnavailable(HTTPException):
    def __init__(self, message: str = UNAVAILABLE) -> None:
        super().__init__(status.HTTP_503_SERVICE_UNAVAILABLE, message)


class HttpPaystack:
    def __init__(self, secret_key: str, base_url: str) -> None:
        self._headers = {"Authorization": f"Bearer {secret_key}"}
        self._base = base_url.rstrip("/")

    async def _call(
        self, method: str, path: str, json: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                res = await client.request(
                    method, f"{self._base}{path}", json=json, headers=self._headers
                )
        except httpx.HTTPError as exc:
            raise PaystackUnavailable() from exc
        body = res.json() if res.content else {}
        if res.status_code >= 500 or not isinstance(body, dict):
            raise PaystackUnavailable()
        if not body.get("status"):
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, f"Paystack: {body.get('message', 'request failed')}"
            )
        return body["data"]

    async def initialize(
        self,
        *,
        email: str,
        amount_kobo: int,
        reference: str,
        callback_url: str,
        subaccount: str | None,
        metadata: dict[str, Any],
    ) -> Checkout:
        payload: dict[str, Any] = {
            "email": email,
            "amount": amount_kobo,
            "currency": "NGN",
            "reference": reference,
            "callback_url": callback_url,
            "metadata": metadata,
        }
        if subaccount:
            # Money settles to the school's own account; the school bears Paystack's fee
            # (decided 2026-10-08), so the parent pays exactly the invoice amount.
            payload |= {"subaccount": subaccount, "bearer": "subaccount"}
        data = await self._call("POST", "/transaction/initialize", payload)
        return Checkout(authorization_url=data["authorization_url"], reference=data["reference"])

    async def verify(self, reference: str) -> Verification:
        data = await self._call("GET", f"/transaction/verify/{reference}")
        return Verification(
            reference=data["reference"],
            success=data.get("status") == "success",
            amount_kobo=int(data.get("amount", 0)),
            currency=data.get("currency", "NGN"),
            raw=data,
        )


def get_paystack() -> PaystackClient:
    """FastAPI dependency. 503 when no key is configured, so the app degrades to transfers."""
    settings = get_settings()
    if settings.paystack_secret_key is None:
        raise PaystackUnavailable(
            "Online payment isn't set up for this school yet. Please pay by bank transfer."
        )
    return HttpPaystack(settings.paystack_secret_key.get_secret_value(), settings.paystack_base_url)


def valid_signature(raw_body: bytes, signature: str | None) -> bool:
    """Paystack signs webhooks with HMAC-SHA512 of the raw body using the secret key."""
    key = get_settings().paystack_secret_key
    if key is None or not signature:
        return False
    expected = hmac.new(key.get_secret_value().encode(), raw_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature)
