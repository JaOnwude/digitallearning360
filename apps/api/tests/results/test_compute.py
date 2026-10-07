"""AC3: the results engine matches an independently computed 40 × 12 fixture exactly."""

import csv
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from app.results.compute import Band, StudentInput, competition_positions, compute_arm, grade_for

FIXTURES = Path(__file__).parent / "fixtures"
COMPONENTS = ["ca1", "ca2", "project", "exam"]
PROGRESS_BANDS = [
    Band("A", "Distinction", 70, 100),
    Band("B", "Excellent", 61, 69),
    Band("C", "Credit", 55, 60),
    Band("P", "Pass", 40, 54),
    Band("F", "Fail", 0, 39),
]


def _id(name: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, name)


def _read(name: str) -> list[dict[str, str]]:
    with (FIXTURES / name).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_ac3_fixture_matches_engine_exactly() -> None:
    scores: dict[str, dict[uuid.UUID, dict[uuid.UUID, Decimal]]] = {}
    earlier: dict[str, dict[uuid.UUID, list[Decimal]]] = {}
    for row in _read("ac3_scores.csv"):
        s, subj = row["admission_no"], _id(row["subject"])
        scores.setdefault(s, {})[subj] = {_id(c): Decimal(row[c]) for c in COMPONENTS}
        earlier.setdefault(s, {})[subj] = [Decimal(row["earlier_term_total"])]
    students = [
        StudentInput(enrollment_id=_id(s), scores=scores[s], earlier_totals=earlier[s])
        for s in scores
    ]
    result = compute_arm(students, PROGRESS_BANDS)

    for row in _read("ac3_expected_subjects.csv"):
        got = result.students[_id(row["admission_no"])].subjects[_id(row["subject"])]
        where = f"{row['admission_no']} {row['subject']}"
        assert got.total == Decimal(row["total"]), where
        assert got.grade == row["grade"], where
        assert got.cumulative_average == Decimal(row["cumulative_average"]), where
        assert got.position == int(row["subject_position"]), where

    expected_students = _read("ac3_expected_students.csv")
    class_row = expected_students.pop()
    assert class_row["admission_no"] == "CLASS_AVERAGE"
    assert result.class_average == Decimal(class_row["average"])
    assert result.number_in_class == 40
    for row in expected_students:
        got = result.students[_id(row["admission_no"])]
        where = row["admission_no"]
        assert got.total == Decimal(row["total"]), where
        assert got.subjects_taken == int(row["subjects_taken"]), where
        assert got.average == Decimal(row["average"]), where
        assert got.position == int(row["position"]), where


@pytest.mark.parametrize(
    ("total", "letter"),
    [("100", "A"), ("69.5", "A"), ("69.49", "B"), ("60.5", "B"), ("60.49", "C"),
     ("54.5", "C"), ("39.5", "P"), ("39.49", "F"), ("0", "F")],
)  # fmt: skip
def test_grade_boundaries_round_half_up(total: str, letter: str) -> None:
    assert grade_for(Decimal(total), PROGRESS_BANDS).letter == letter


def test_competition_ranking_ties_skip() -> None:
    values = {"a": Decimal(90), "b": Decimal(80), "c": Decimal(80), "d": Decimal(70)}
    assert competition_positions(values) == {"a": 1, "b": 2, "c": 2, "d": 4}


def test_student_with_no_scores_has_no_position_and_is_left_out_of_class_average() -> None:
    subj, comp = uuid.uuid4(), uuid.uuid4()
    a = StudentInput(uuid.uuid4(), {subj: {comp: Decimal(80)}})
    absent = StudentInput(uuid.uuid4(), {})
    result = compute_arm([a, absent], PROGRESS_BANDS)
    assert result.students[absent.enrollment_id].position is None
    assert result.number_in_class == 2
    assert result.class_average == Decimal("80.00")
