"""Invoice and receipt PDFs (R20), in the same visual language as report cards."""

import io
from datetime import datetime
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable,
    Image,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.fees.ledger import naira
from app.fees.schemas import EntryOut, InvoiceDetail
from app.reports.pdf import GRID, H_BIG, H_SMALL, SHADE, SMALL, TXT, TXT_B, H, _p


def _header(
    school_name: str, address: str | None, title: str, logo: bytes | None
) -> list[Flowable]:
    lines = [_p(school_name.upper(), H_BIG)]
    if address:
        lines.append(_p(address, H_SMALL))
    lines.append(_p(title, H))
    text = Table([[x] for x in lines], colWidths=[138 * mm])
    logo_cell: Flowable = Spacer(20 * mm, 20 * mm)
    if logo:
        logo_cell = Image(io.BytesIO(logo), width=20 * mm, height=20 * mm, kind="proportional")
    t = Table([[logo_cell, text, Spacer(20 * mm, 1)]], colWidths=[24 * mm, 138 * mm, 24 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    return [t, Spacer(1, 4 * mm)]


def _kv(rows: list[tuple[str, str]]) -> Table:
    t = Table([[_p(k, TXT_B), _p(v, TXT)] for k, v in rows], colWidths=[40 * mm, 146 * mm])
    t.setStyle(
        TableStyle([("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)])
    )
    return t


def _doc(title: str) -> tuple[io.BytesIO, SimpleDocTemplate]:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=title,
        author="DigitalLearning360",
    )
    return buf, doc


def invoice_pdf(
    d: InvoiceDetail, *, school_name: str, address: str | None, logo: bytes | None
) -> bytes:
    buf, doc = _doc(f"Invoice {d.reference}")
    lines: list[list[Any]] = [[_p("DESCRIPTION", TXT_B), _p("AMOUNT", TXT_B)]]
    lines += [[_p(line.description, TXT), naira(line.amount_kobo)] for line in d.lines]
    lines.append([_p("TOTAL", TXT_B), naira(d.total_kobo)])
    for e in d.entries:
        label = {
            "payment": f"Paid ({e.source.value})",
            "refund": "Refund",
            "adjustment": e.note or "Adjustment",
        }
        sign = -1 if e.kind.value == "payment" else 1
        lines.append(
            [
                _p(f"{label[e.kind.value]} · {e.created_at:%d %b %Y}", TXT),
                naira(sign * e.amount_kobo),
            ]
        )
    lines.append([_p("BALANCE DUE", TXT_B), naira(max(d.balance_kobo, 0))])
    t = Table(lines, colWidths=[146 * mm, 40 * mm])
    t.setStyle(
        TableStyle(
            [
                *GRID,
                ("BACKGROUND", (0, 0), (-1, 0), SHADE),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("BACKGROUND", (0, -1), (-1, -1), SHADE),
                ("FONT", (1, -1), (1, -1), "Helvetica-Bold", 9),
            ]
        )
    )
    story: list[Flowable] = [
        *_header(school_name, address, "INVOICE", logo),
        _kv(
            [
                ("Invoice no.", d.reference),
                ("Student", f"{d.student_name} ({d.admission_no})"),
                ("Class", d.class_label or "—"),
                ("Term", d.term_label),
                ("Due", f"{d.due_on:%d %B %Y}" if d.due_on else "—"),
            ]
        ),
        Spacer(1, 4 * mm),
        t,
        Spacer(1, 5 * mm),
    ]
    if d.bank.account_number:
        story += [
            _p("PAY BY BANK TRANSFER", TXT_B),
            _kv(
                [
                    ("Bank", d.bank.bank_name or ""),
                    ("Account name", d.bank.account_name or ""),
                    ("Account number", d.bank.account_number),
                    ("Narration", d.reference),
                ]
            ),
            _p(
                "Then upload your transfer receipt on the school portal for the bursar to confirm.",
                SMALL,
            ),
        ]
    story += [
        Spacer(1, 6 * mm),
        _p(f"Generated {datetime.now():%d %b %Y} · DigitalLearning360", SMALL),
    ]
    doc.build(story)
    return buf.getvalue()


def receipt_pdf(
    d: InvoiceDetail, entry: EntryOut, *, school_name: str, address: str | None, logo: bytes | None
) -> bytes:
    buf, doc = _doc(f"Receipt {entry.receipt_no}")
    how = {
        "paystack": "Online (Paystack)",
        "transfer": "Bank transfer",
        "cash": "Cash",
        "manual": "Other",
    }
    story: list[Flowable] = [
        *_header(school_name, address, "OFFICIAL RECEIPT", logo),
        _kv(
            [
                ("Receipt no.", entry.receipt_no or ""),
                ("Date", f"{entry.created_at:%d %B %Y}"),
                ("Received from", f"Parent/guardian of {d.student_name}"),
                ("Student", f"{d.student_name} ({d.admission_no}) · {d.class_label or ''}"),
                ("For", f"Invoice {d.reference} · {d.term_label}"),
                ("Paid by", how.get(entry.source.value, entry.source.value)),
            ]
        ),
        Spacer(1, 5 * mm),
    ]
    amount = Table(
        [
            [_p("AMOUNT RECEIVED", TXT_B), naira(entry.amount_kobo)],
            [_p("CURRENT BALANCE ON INVOICE", TXT_B), naira(max(d.balance_kobo, 0))],
        ],
        colWidths=[146 * mm, 40 * mm],
    )
    amount.setStyle(
        TableStyle(
            [
                *GRID,
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("BACKGROUND", (0, 0), (-1, 0), SHADE),
                ("FONT", (1, 0), (1, 0), "Helvetica-Bold", 11),
            ]
        )
    )
    story += [
        amount,
        Spacer(1, 8 * mm),
        _p("This receipt was issued electronically and is valid without a signature.", SMALL),
    ]
    doc.build(story)
    return buf.getvalue()
