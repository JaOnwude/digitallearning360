"""CSV exports open safely in Excel (no formula injection)."""

from app.fees.router import _csv


def test_formula_like_text_is_neutralised() -> None:
    body = _csv(
        [["Name", "Balance"], ['=HYPERLINK("http://x")', 4500000], ["-2+3", -500], ["Ada", 0]],
        "t.csv",
    ).body
    body = bytes(body).decode()
    assert "'=HYPERLINK" in body and "'-2+3" in body
    assert ",-500" in body  # numbers stay numbers
    assert "\nAda,0" in body.replace("\r", "")
