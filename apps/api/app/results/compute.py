"""Turn raw scores into term results (spec R16, AC3). Pure functions: no database, no I/O.

Rules (confirmed with the school owner, 2026-10-07):
- Subject total = sum of the subject's component scores. A subject with no scores at all
  was not taken and is left out of the student's totals.
- Grade = the band containing the total rounded half-up to a whole mark (69.5 → 70).
- Student total = sum of subject totals; average = total ÷ subjects taken (2 d.p.).
- Class average = mean of the averages of students who took at least one subject.
- Cumulative average per subject = mean of that subject's totals for every term so far
  this session, this term included.
- Positions use competition ranking: equal values share a position and the next one skips
  (1, 2, 2, 4). Computed always; whether they are printed is a per-section setting.
"""

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

TWO_DP = Decimal("0.01")


@dataclass(frozen=True)
class Band:
    letter: str
    descriptor: str
    min_score: int
    max_score: int


@dataclass(frozen=True)
class StudentInput:
    enrollment_id: uuid.UUID
    # subject → component → score (missing components simply absent)
    scores: dict[uuid.UUID, dict[uuid.UUID, Decimal]]
    # subject → totals from earlier terms this session (for the cumulative average)
    earlier_totals: dict[uuid.UUID, list[Decimal]] = field(default_factory=dict)


@dataclass(frozen=True)
class SubjectResult:
    subject_id: uuid.UUID
    component_scores: dict[uuid.UUID, Decimal]
    total: Decimal
    grade: str
    descriptor: str
    cumulative_average: Decimal
    position: int


@dataclass(frozen=True)
class StudentResult:
    enrollment_id: uuid.UUID
    subjects: dict[uuid.UUID, SubjectResult]
    total: Decimal
    subjects_taken: int
    average: Decimal
    position: int | None  # None when the student took no subjects


@dataclass(frozen=True)
class ArmResult:
    students: dict[uuid.UUID, StudentResult]
    number_in_class: int
    class_average: Decimal


def round_half_up(value: Decimal, quantum: Decimal = TWO_DP) -> Decimal:
    return value.quantize(quantum, rounding=ROUND_HALF_UP)


def grade_for(total: Decimal, bands: Sequence[Band]) -> Band:
    mark = int(total.quantize(Decimal(1), rounding=ROUND_HALF_UP))
    for band in bands:
        if band.min_score <= mark <= band.max_score:
            return band
    raise ValueError(f"No grade band covers {mark}")  # config validation prevents this


def competition_positions[K](values: dict[K, Decimal]) -> dict[K, int]:
    """1 + the number of strictly higher values: ties share a position, the next skips."""
    ordered = sorted(values.values(), reverse=True)
    first_index = {}
    for i, v in enumerate(ordered):
        first_index.setdefault(v, i + 1)
    return {k: first_index[v] for k, v in values.items()}


def _mean(values: Iterable[Decimal]) -> Decimal:
    items = list(values)
    return round_half_up(sum(items, Decimal(0)) / len(items))


def compute_arm(students: Sequence[StudentInput], bands: Sequence[Band]) -> ArmResult:
    totals: dict[uuid.UUID, dict[uuid.UUID, Decimal]] = {}
    for s in students:
        totals[s.enrollment_id] = {
            subject: sum(cells.values(), Decimal(0)) for subject, cells in s.scores.items() if cells
        }

    subject_ids = {subj for per in totals.values() for subj in per}
    subject_positions: dict[uuid.UUID, dict[uuid.UUID, int]] = {}
    for subj in subject_ids:
        taking = {e: per[subj] for e, per in totals.items() if subj in per}
        subject_positions[subj] = competition_positions(taking)

    averages: dict[uuid.UUID, Decimal] = {}
    partial: dict[uuid.UUID, tuple[dict[uuid.UUID, SubjectResult], Decimal, int]] = {}
    for s in students:
        per = totals[s.enrollment_id]
        subject_results = {}
        for subj, total in per.items():
            band = grade_for(total, bands)
            subject_results[subj] = SubjectResult(
                subject_id=subj,
                component_scores=dict(s.scores[subj]),
                total=total,
                grade=band.letter,
                descriptor=band.descriptor,
                cumulative_average=_mean([*s.earlier_totals.get(subj, []), total]),
                position=subject_positions[subj][s.enrollment_id],
            )
        grand_total = sum(per.values(), Decimal(0))
        taken = len(per)
        if taken:
            averages[s.enrollment_id] = round_half_up(grand_total / taken)
        partial[s.enrollment_id] = (subject_results, grand_total, taken)

    positions = competition_positions(averages)
    results = {
        e: StudentResult(
            enrollment_id=e,
            subjects=subject_results,
            total=grand_total,
            subjects_taken=taken,
            average=averages.get(e, Decimal("0.00")),
            position=positions.get(e),
        )
        for e, (subject_results, grand_total, taken) in partial.items()
    }
    return ArmResult(
        students=results,
        number_in_class=len(students),
        class_average=_mean(averages.values()) if averages else Decimal("0.00"),
    )
