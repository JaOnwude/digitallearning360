"""R26: payment start and proof uploads are rate limited per user."""

from tests.conftest import ClientFactory
from tests.fees.conftest import TUITION_KOBO, FeesWorld
from tests.fees.fake_paystack import FakePaystack

JPEG = b"\xff\xd8\xff\xe0" + b"receipt" * 20


async def test_starting_payments_is_rate_limited(
    fees_world: FeesWorld, client_for: ClientFactory, paystack: FakePaystack
) -> None:
    parent = await fees_world.parent(client_for)
    url = f"/api/fees/invoices/{fees_world.invoice_ids[0]}/paystack"
    for _ in range(10):
        assert (await parent.post(url)).status_code == 200
    blocked = await parent.post(url)
    assert blocked.status_code == 429 and "Retry-After" in blocked.headers


async def test_proof_uploads_are_rate_limited(
    fees_world: FeesWorld, client_for: ClientFactory
) -> None:
    parent = await fees_world.parent(client_for)
    url = f"/api/fees/invoices/{fees_world.invoice_ids[0]}/proofs"

    async def upload(i: int) -> int:
        res = await parent.post(
            url,
            files={"file": ("r.jpg", JPEG + bytes([i]), "image/jpeg")},
            data={"amount_kobo": str(TUITION_KOBO)},
        )
        return res.status_code

    for i in range(10):
        assert await upload(i) == 201
    assert await upload(10) == 429
