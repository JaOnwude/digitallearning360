from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.auth.models import Role
from app.fees.models import FeeItem, FeeScheduleEntry
from app.fees.paystack import get_paystack
from tests.conftest import ClientFactory
from tests.factories import ResultsWorld, make_results_world, tenant_session
from tests.fees.fake_paystack import FakePaystack
from tests.helpers import signed_in, signed_in_parent

TUITION_KOBO = 4_500_000  # ₦45,000


@pytest.fixture
def paystack(app_instance: FastAPI) -> Iterator[FakePaystack]:
    fake = FakePaystack()
    app_instance.dependency_overrides[get_paystack] = lambda: fake
    yield fake
    app_instance.dependency_overrides.pop(get_paystack, None)


@dataclass
class FeesWorld:
    w: ResultsWorld
    admin: AsyncClient
    bursar: AsyncClient
    invoice_ids: list[str]  # one per student, same order as w.students

    async def parent(self, client_for: ClientFactory, i: int = 0) -> AsyncClient:
        detail = (await self.admin.get(f"/api/students/{self.w.students[i].id}")).json()
        return await signed_in_parent(client_for, self.w.school, detail["guardians"][0]["email"])


@pytest.fixture
async def fees_world(client_for: ClientFactory) -> FeesWorld:
    """A JSS1 A class with ₦45,000 tuition this term and invoices already issued."""
    w = await make_results_world(n_students=3)
    async with tenant_session(w.school) as db:
        item = FeeItem(school_id=w.school.id, name="Tuition")
        db.add(item)
        await db.flush()
        db.add(FeeScheduleEntry(school_id=w.school.id, fee_item_id=item.id, class_level_id=w.structure.level.id,
                                term_id=w.term.id, amount_kobo=TUITION_KOBO))  # fmt: skip
    admin = await signed_in(client_for, w.school, Role.SCHOOL_ADMIN)
    bursar = await signed_in(client_for, w.school, Role.BURSAR)
    res = await bursar.post("/api/fees/invoices/generate", json={})
    assert res.json()["created"] == 3, res.text
    rows = (await bursar.get("/api/fees/invoices")).json()["items"]
    by_student = {r["student_id"]: r["id"] for r in rows}
    return FeesWorld(
        w=w, admin=admin, bursar=bursar, invoice_ids=[by_student[str(s.id)] for s in w.students]
    )
