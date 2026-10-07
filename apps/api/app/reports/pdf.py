"""Report card PDFs, drawn from a published snapshot (spec R17, AC3a, AC5).

One A4 portrait page per student. Two layouts share these building blocks:
- `ebonyi_jss`: Progress JSS's paper sheet (docs/pilot-school/result-template.pdf)
- `standard`: a clean default for schools whose own template isn't built yet
"""

import io
from typing import Any

import segno
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable,
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

INK = colors.HexColor("#111111")
MUTED = colors.HexColor("#555555")
RULE = colors.HexColor("#333333")
SHADE = colors.HexColor("#EFEFEF")

H = ParagraphStyle(
    "h", fontName="Helvetica-Bold", fontSize=10.5, leading=13, alignment=TA_CENTER, textColor=INK
)
H_BIG = ParagraphStyle("hb", parent=H, fontSize=13, leading=16)
H_SMALL = ParagraphStyle("hs", parent=H, fontSize=9, leading=11)
TXT = ParagraphStyle("t", fontName="Helvetica", fontSize=8, leading=10, textColor=INK)
TXT_B = ParagraphStyle("tb", parent=TXT, fontName="Helvetica-Bold")
SMALL = ParagraphStyle("s", parent=TXT, fontSize=6.5, leading=8, textColor=MUTED)


def _p(text: str | None, style: ParagraphStyle = TXT) -> Paragraph:
    from xml.sax.saxutils import escape

    return Paragraph(escape(text or ""), style)


class Field(Flowable):
    """ "LABEL: value_____" like a printed form, with the value written on the line."""

    def __init__(self, label: str, value: str | None, width: float) -> None:
        super().__init__()
        self.label, self.value, self.width, self.height = label, value or "", width, 5.2 * mm

    def draw(self) -> None:
        c = self.canv
        c.setFont("Helvetica-Bold", 7.5)
        c.setFillColor(INK)
        c.drawString(0, 1.4 * mm, f"{self.label}:")
        lw = c.stringWidth(f"{self.label}: ", "Helvetica-Bold", 7.5)
        c.setStrokeColor(MUTED)
        c.setLineWidth(0.4)
        c.line(lw, 0.8 * mm, self.width - 1.5 * mm, 0.8 * mm)
        c.setFont("Helvetica", 8.5)
        c.drawString(lw + 1 * mm, 1.5 * mm, self.value)


def _fields(row: list[tuple[str, str | None, float]]) -> Table:
    t = Table(
        [[Field(label, value, w * mm) for label, value, w in row]],
        colWidths=[w * mm for *_, w in row],
    )
    t.setStyle(TableStyle([(side, (0, 0), (-1, -1), 0) for side in NO_PAD]))
    return t


NO_PAD = ("LEFTPADDING", "RIGHTPADDING", "TOPPADDING", "BOTTOMPADDING")


GRID = [
    ("GRID", (0, 0), (-1, -1), 0.5, RULE),
    ("FONT", (0, 0), (-1, -1), "Helvetica", 8),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("TOPPADDING", (0, 0), (-1, -1), 1.2),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2),
    ("LEFTPADDING", (0, 0), (-1, -1), 2),
    ("RIGHTPADDING", (0, 0), (-1, -1), 2),
]


def _header(d: dict[str, Any], logo: bytes | None) -> list[Flowable]:
    report, school = d["report"], d["school"]
    lines: list[Flowable] = [_p(h, H_SMALL) for h in report.get("header_lines") or []]
    name = report.get("section_name") or school["name"]
    if report["template"] == "ebonyi_jss" and school.get("address"):
        name = f"{name} {school['address'].split(',')[0]}"
    lines.append(_p(name.upper(), H_BIG))
    if report.get("title"):
        lines.append(_p(report["title"].upper(), H))
    if report.get("subtitle"):
        lines.append(_p(report["subtitle"].upper(), H_SMALL))
    text_col = Table([[x] for x in lines], colWidths=[140 * mm])
    text_col.setStyle(
        TableStyle(
            [("TOPPADDING", (0, 0), (-1, -1), 0.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 0.5)]
        )
    )
    logo_cell: Flowable = Spacer(22 * mm, 22 * mm)
    if logo:
        logo_cell = Image(io.BytesIO(logo), width=22 * mm, height=22 * mm, kind="proportional")
    t = Table([[logo_cell, text_col, Spacer(22 * mm, 1)]], colWidths=[24 * mm, 138 * mm, 24 * mm])
    t.setStyle(
        TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (0, 0), "LEFT")])
    )
    return [t, Spacer(1, 2 * mm)]


def _student_fields(d: dict[str, Any]) -> list[Flowable]:
    st, term, summary = d["student"], d["term"], d["summary"]
    last: list[tuple[str, str | None, float]] = [("CLASS AVERAGE", summary["class_average"], 62)]
    if d["report"]["template"] != "ebonyi_jss":  # Progress's sheet has no student average line
        last.append(("STUDENT'S AVERAGE", summary["average"], 62))
    if d["report"].get("show_positions") and summary.get("position"):
        last.append(("POSITION", f"{summary['position']} of {summary['number_in_class']}", 62))
    rows = [
        [("NAME OF STUDENT", st["name"], 128), ("HOUSE", st.get("house"), 58)],
        [
            ("CLASS", st["class_label"], 46),
            ("NUMBER IN CLASS", str(summary["number_in_class"]), 44),
            ("TERM", term.get("name"), 46),
            ("YEAR", term["session"], 50),
        ],
        [
            ("NEXT TERM BEGINS", _date(term.get("next_term_begins")), 76),
            ("NUMBER OF SUBJECTS", str(summary["subjects_taken"]), 54),
            ("TOTAL SCORE", summary["total"], 56),
        ],
        last,
    ]
    out: list[Flowable] = []
    for row in rows:
        out += [_fields(row), Spacer(1, 0.8 * mm)]
    return [*out, Spacer(1, 1.5 * mm)]


def _date(iso: str | None) -> str:
    if not iso:
        return ""
    y, m, day = iso.split("-")
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{int(day)} {months[int(m) - 1]} {y}"


def _subjects_table(d: dict[str, Any]) -> Table:
    comps = d["components"]
    show_pos = bool(d["report"].get("show_positions"))
    head = [
        "",
        "SUBJECTS",
        *[c["name"].upper() for c in comps],
        "TOTAL SCORE",
        "GRADE",
        "CUM. AVERAGE",
    ]
    sub = ["", "", *[f"{c['max_score']}%" for c in comps], "100%", "", "%"]
    if show_pos:
        head.append("POS.")
        sub.append("")
    body = []
    for i, s in enumerate(d["subjects"], 1):
        row = [str(i), _p(s["name"].upper(), TXT), *[x or "" for x in s["scores"]],
               s["total"] or "", s["grade"] or "", s["cumulative_average"] or ""]  # fmt: skip
        if show_pos:
            row.append(str(s["position"] or ""))
        body.append(row)
    widths = [
        7 * mm,
        52 * mm,
        *[(78 / max(len(comps), 1)) * mm] * len(comps),
        16 * mm,
        13 * mm,
        19 * mm,
    ]
    if show_pos:
        widths = [w * 0.94 for w in widths] + [11 * mm]
    head_cells = [
        _p(h, ParagraphStyle("hc", parent=TXT_B, fontSize=6.5, leading=7.5, alignment=TA_CENTER))
        for h in head
    ]
    t = Table([head_cells, sub, *body], colWidths=widths, repeatRows=2)
    t.setStyle(TableStyle([*GRID,
        ("BACKGROUND", (0, 0), (-1, 1), SHADE),
        ("ALIGN", (2, 1), (-1, -1), "CENTER"), ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("FONT", (0, 1), (-1, 1), "Helvetica-Bold", 7),
        ("FONT", (-3, 2), (-2, -1), "Helvetica-Bold", 8.5),
    ]))  # fmt: skip
    return t


def _grade_key(d: dict[str, Any]) -> Table:
    parts = [f"{g['letter']} = ({g['descriptor'].upper()}) {_range(g)}" for g in d["grade_key"]]
    t = Table(
        [[_p("KEY TO GRADES", TXT_B), _p("   ·   ".join(parts), TXT)]],
        colWidths=[26 * mm, 160 * mm],
    )
    t.setStyle(TableStyle([*GRID, ("BACKGROUND", (0, 0), (0, 0), SHADE)]))
    return t


def _range(g: dict[str, Any]) -> str:
    if g["max"] >= 100:
        return f"{g['min']}% AND ABOVE"
    if g["min"] <= 0:
        return f"BELOW {g['max'] + 1}%"
    return f"{g['min']}–{g['max']}%"


def _ratings(d: dict[str, Any]) -> Table | None:
    groups = d.get("trait_groups") or []
    if not groups:
        return None

    def group_table(g: dict[str, Any]) -> Table:
        rows: list[list[Any]] = [[_p(g["name"].upper(), TXT_B), "1", "2", "3", "4", "5"]]
        for i, tr in enumerate(g["traits"], 1):
            rows.append(
                [
                    _p(f"{i}  {tr['name'].upper()}", TXT),
                    *["X" if tr["value"] == v else "" for v in range(1, 6)],
                ]
            )
        t = Table(rows, colWidths=[52 * mm, *[6 * mm] * 5])
        t.setStyle(TableStyle([*GRID, ("BACKGROUND", (0, 0), (-1, 0), SHADE),
                               ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                               ("FONT", (1, 1), (-1, -1), "Helvetica-Bold", 8)]))  # fmt: skip
        return t

    tables: list[Any] = [group_table(g) for g in groups[:2]]
    key = _p("KEY TO RATING: 5 – EXCELLENT · 4 – GOOD · 3 – FAIR · 2 – POOR · 1 – VERY POOR", SMALL)
    if len(tables) == 1:
        tables.append("")
    t = Table([tables, [key, ""]], colWidths=[93 * mm, 93 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("SPAN", (0, 1), (1, 1)),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0)]))  # fmt: skip
    return t


def _comments(d: dict[str, Any]) -> Table:
    rows: list[list[Any]] = []
    for c in d["comments"]:
        rows.append([_p(c["label"].upper(), TXT_B)])
        rows.append([_p(c["text"] or " ", TXT)])
    promo = d.get("promotion")
    if d["term"]["number"] == 3:
        marks = (
            {True: ("X", " "), False: (" ", "X")}.get(promo, (" ", " "))
            if promo is not None
            else (" ", " ")
        )
        rows.append([_p(f"PROMOTED  [{marks[0]}]      NOT PROMOTED  [{marks[1]}]", TXT_B)])
    rows.append([_p("DATE AND STAMP: ____________________________", TXT)])
    t = Table(rows, colWidths=[186 * mm])
    style = [*GRID]
    for i in range(0, len(d["comments"]) * 2, 2):
        style.append(("BACKGROUND", (0, i), (-1, i), SHADE))
    t.setStyle(TableStyle(style))
    return t


def _footer(d: dict[str, Any], verify_url: str, short_hash: str) -> Table:
    qr = io.BytesIO()
    segno.make(verify_url, error="m").save(qr, kind="png", scale=3, border=1)
    qr.seek(0)
    motto = d["school"].get("motto")
    left = [
        _p(f"MOTTO: {motto.upper()}" if motto else "", TXT_B),
        Spacer(1, 1.5 * mm),
        _p(f"Scan to verify this report card · Ref {short_hash}", SMALL),
        _p(f"Published {d['published_at'][:10]} · DigitalLearning360", SMALL),
    ]
    t = Table([[left, Image(qr, width=18 * mm, height=18 * mm)]], colWidths=[166 * mm, 20 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))
    return t


def card_flowables(
    d: dict[str, Any], logo: bytes | None, verify_url: str, short_hash: str
) -> list[Flowable]:
    out: list[Flowable] = [
        *_header(d, logo),
        *_student_fields(d),
        _subjects_table(d),
        Spacer(1, 1.5 * mm),
        _grade_key(d),
        Spacer(1, 2.5 * mm),
    ]
    ratings = _ratings(d)
    if ratings is not None:
        out += [ratings, Spacer(1, 2.5 * mm)]
    out += [KeepTogether([_comments(d), Spacer(1, 2 * mm), _footer(d, verify_url, short_hash)])]
    return out


def render(cards: list[tuple[dict[str, Any], str, str]], logo: bytes | None, title: str) -> bytes:
    """`cards` = [(snapshot data, verify URL, short hash)]. One page per card."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
        title=title,
        author="DigitalLearning360",
    )
    story: list[Flowable] = []
    for i, (data, url, short) in enumerate(cards):
        if i:
            story.append(PageBreak())
        story += card_flowables(data, logo, url, short)
    doc.build(story)
    return buf.getvalue()
