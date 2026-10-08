"""CSV exports open safely in Excel (no formula injection)."""

import csv
import io

from app.fees.router import _csv
from tests.fees.conftest import FeesWorld


def test_formula_like_text_is_neutralised() -> None:
    body = _csv(
        [["Name", "Balance"], ['=HYPERLINK("http://x")', 4500000], ["-2+3", -500], ["Ada", 0]],
        "t.csv",
    ).body
    body = bytes(body).decode()
    assert "'=HYPERLINK" in body and "'-2+3" in body
    assert ",-500" in body  # numbers stay numbers
    assert "\nAda,0" in body.replace("\r", "")


async def test_debtors_csv_columns_add_up(fees_world: FeesWorld) -> None:
    """Fees + waivers/charges - paid = balance, in exact naira (no floats)."""
    bursar, inv = fees_world.bursar, fees_world.invoice_ids[0]
    await bursar.post(
        f"/api/fees/invoices/{inv}/adjustments",
        json={"amount_kobo": -500_000, "note": "Scholarship"},
    )
    await bursar.post(f"/api/fees/invoices/{inv}/payments", json={"amount_kobo": 1_000_050})
    rows = list(
        csv.reader(io.StringIO((await bursar.get("/api/fees/exports/debtors.csv")).text.lstrip("﻿")))
    )
    header, row = (
        rows[0],
        next(r for r in rows if r[0] and r[0] != "Invoice" and r[4] and r[5] != "0.00"),
    )
    assert header[4:] == ["Fees (NGN)", "Waivers / charges (NGN)", "Paid (NGN)", "Balance (NGN)"]
    assert row[4:] == ["45000.00", "-5000.00", "10000.50", "29999.50"]
