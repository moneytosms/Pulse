"""P4.1 (#52) — pure duplicate-pair scoring, no DB.

Seam: `score_pair`. Weighting is name 0.5 / DOB 0.3 / phone 0.2
(domain-model.md, "Duplicate detection"). Cases below are drawn straight
from the planted pairs in `seed/data/identity/planted_pairs.csv` so the
expected classification (duplicate vs. not) comes from an independent
source — the manifest's own `kind` column — not from this function's own
arithmetic.

Negative test first: a near-miss (shared surname, real name/DOB/phone
differences) must score below the duplicate threshold.
"""

from __future__ import annotations

from datetime import date

from app.modules.users.service import DUPLICATE_THRESHOLD, PatientIdentity, score_pair


def test_near_miss_sibling_pair_does_not_score_as_a_duplicate() -> None:
    # planted_pairs.csv: sibling_same_surname_adjacent_dob — same surname
    # only, different given name, DOB 2y apart, different phone.
    a = PatientIdentity(
        full_name="स्वर्ण बुरुाहजी", date_of_birth=date(1965, 7, 12), phone="+91 90000 95244"
    )
    b = PatientIdentity(
        full_name="संमानित बुरुाहजी", date_of_birth=date(1967, 7, 12), phone="+91 90000 14987"
    )

    assert score_pair(a, b) < DUPLICATE_THRESHOLD


def test_token_order_swap_scores_as_a_duplicate() -> None:
    # planted_pairs.csv: token_order_swap — same tokens reordered, same
    # DOB, same phone. Token-sort normalisation makes the names identical.
    a = PatientIdentity(
        full_name="ଶ୍ରୀମତୀ ଭବାନୀ ଦେବି", date_of_birth=date(1976, 12, 7), phone="+91 90000 79547"
    )
    b = PatientIdentity(
        full_name="ଦେବି ଶ୍ରୀମତୀ ଭବାନୀ", date_of_birth=date(1976, 12, 7), phone="+91 90000 79547"
    )

    assert score_pair(a, b) >= DUPLICATE_THRESHOLD


def test_dob_typo_scores_as_a_duplicate() -> None:
    # planted_pairs.csv: dob_typo — same name, same phone, DOB off by 2
    # days (transposition tolerance).
    a = PatientIdentity(
        full_name="யூவராஜ் ரீட்டா", date_of_birth=date(2019, 12, 10), phone="+91 90000 30191"
    )
    b = PatientIdentity(
        full_name="யூவராஜ் ரீட்டா", date_of_birth=date(2019, 12, 8), phone="+91 90000 30191"
    )

    assert score_pair(a, b) >= DUPLICATE_THRESHOLD


def test_identical_identity_scores_one() -> None:
    a = PatientIdentity(full_name="Aishani Toor", date_of_birth=date(1962, 1, 13), phone="x")
    assert score_pair(a, a) == 1.0
