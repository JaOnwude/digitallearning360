"""Generate the AC3 fixture: 40 students × 12 subjects with expected results.

The expected values are computed here with exact fractions, independently of
app/results/compute.py, so the test compares two separate implementations. The CSVs are
committed so anyone can check rows by hand in a spreadsheet. Regenerate with:

    uv run python -m tests.results.make_ac3_fixture
"""

import csv
import random
from fractions import Fraction
from pathlib import Path

OUT = Path(__file__).parent / "fixtures"
MAXES = {"ca1": 10, "ca2": 10, "project": 10, "exam": 70}
BANDS = [("A", 70, 100), ("B", 61, 69), ("C", 55, 60), ("P", 40, 54), ("F", 0, 39)]
SUBJECTS = [f"S{i:02d}" for i in range(1, 13)]


def grade(total: Fraction) -> str:
    mark = int(total + Fraction(1, 2))  # half-up for non-negative values
    return next(letter for letter, lo, hi in BANDS if lo <= mark <= hi)


def two_dp(x: Fraction) -> str:
    cents = int(x * 100 + Fraction(1, 2))  # half-up
    return f"{cents // 100}.{cents % 100:02d}"


def positions(values: dict[str, Fraction]) -> dict[str, int]:
    return {k: 1 + sum(1 for o in values.values() if o > v) for k, v in values.items()}


def main() -> None:
    rng = random.Random(360)  # noqa: S311 - deterministic test data, not security
    students = [f"PJS{i:03d}" for i in range(1, 41)]
    scores: dict[str, dict[str, dict[str, Fraction]]] = {}
    earlier: dict[str, dict[str, Fraction]] = {}
    for s in students:
        scores[s] = {}
        earlier[s] = {}
        for subj in SUBJECTS:
            if s == "PJS040" and subj == "S12":
                continue  # one student doesn't take one subject
            row = {k: Fraction(rng.randint(m // 3, m) * 2, 2) for k, m in MAXES.items()}
            if rng.random() < 0.15:
                row["exam"] += Fraction(1, 2)  # half marks happen
                row["exam"] = min(row["exam"], Fraction(70))
            scores[s][subj] = row
            earlier[s][subj] = Fraction(rng.randint(30, 95))
    # Deliberate edge cases.
    scores["PJS001"]["S01"] = {
        "ca1": Fraction(10),
        "ca2": Fraction(10),
        "project": Fraction(9),
        "exam": Fraction(81, 2),
    }  # 69.5 → A
    scores["PJS002"]["S01"] = {
        "ca1": Fraction(9),
        "ca2": Fraction(9),
        "project": Fraction(9),
        "exam": Fraction(67, 2),
    }  # 60.5 → B
    scores["PJS003"]["S01"] = {
        "ca1": Fraction(5),
        "ca2": Fraction(5),
        "project": Fraction(5),
        "exam": Fraction(49, 2),
    }  # 39.5 → P
    scores["PJS004"] = {k: dict(v) for k, v in scores["PJS005"].items()}  # identical students → tie
    earlier["PJS004"] = dict(earlier["PJS005"])

    totals = {
        s: {subj: sum(c.values(), Fraction(0)) for subj, c in per.items()}
        for s, per in scores.items()
    }
    averages = {s: sum(t.values(), Fraction(0)) / len(t) for s, t in totals.items()}
    # Positions are on the 2-d.p. average shown on the card.
    shown = {s: Fraction(two_dp(a)) for s, a in averages.items()}
    pos = positions(shown)
    class_avg = sum(shown.values(), Fraction(0)) / len(shown)

    with (OUT / "ac3_scores.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["admission_no", "subject", *MAXES, "earlier_term_total"])
        for s in students:
            for subj, c in scores[s].items():
                w.writerow([s, subj, *(float(c[k]) for k in MAXES), float(earlier[s][subj])])
    with (OUT / "ac3_expected_subjects.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            ["admission_no", "subject", "total", "grade", "cumulative_average", "subject_position"]
        )
        for subj in SUBJECTS:
            taking = {s: totals[s][subj] for s in students if subj in totals[s]}
            sp = positions(taking)
            for s, t in taking.items():
                cum = (earlier[s][subj] + t) / 2
                w.writerow([s, subj, two_dp(t), grade(t), two_dp(cum), sp[s]])
    with (OUT / "ac3_expected_students.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["admission_no", "total", "subjects_taken", "average", "position"])
        for s in students:
            w.writerow(
                [
                    s,
                    two_dp(sum(totals[s].values(), Fraction(0))),
                    len(totals[s]),
                    two_dp(averages[s]),
                    pos[s],
                ]
            )
        w.writerow(["CLASS_AVERAGE", "", "", two_dp(class_avg), ""])


if __name__ == "__main__":
    main()
