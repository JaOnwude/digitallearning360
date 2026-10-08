"""A stand-in for Paystack: records calls and answers like the real API would."""

from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException, status

from app.fees.paystack import Checkout, Verification


@dataclass
class FakePaystack:
    initialized: list[dict[str, Any]] = field(default_factory=list)
    verify_calls: int = 0
    # reference → (success, amount actually paid); default: paid in full
    outcomes: dict[str, tuple[bool, int]] = field(default_factory=dict)
    # reference → Paystack status for unsuccessful ones (e.g. "ongoing"); default "failed"
    statuses: dict[str, str] = field(default_factory=dict)

    async def initialize(self, **kwargs: Any) -> Checkout:
        self.initialized.append(kwargs)
        ref = kwargs["reference"]
        return Checkout(authorization_url=f"https://checkout.paystack.test/{ref}", reference=ref)

    async def verify(self, reference: str) -> Verification:
        self.verify_calls += 1
        started = next((i for i in self.initialized if i["reference"] == reference), None)
        if started is None:  # like Paystack: "Transaction reference not found"
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Paystack: reference not found")
        success, amount = self.outcomes.get(reference, (True, started["amount_kobo"]))
        return Verification(
            reference=reference,
            success=success,
            amount_kobo=amount,
            currency="NGN",
            raw={
                "reference": reference,
                "status": "success" if success else self.statuses.get(reference, "failed"),
                "amount": amount,
            },
        )
