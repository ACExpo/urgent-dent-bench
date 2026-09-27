import pytest

from urgentdentbench.agreement import (
    BINARY,
    agreement_table,
    cohen_kappa,
    format_agreement,
    gwet_ac1,
    matched_responses,
    observed_agreement,
)

CASE = {
    "case_id": "CR900-BASE", "anchor_id": "CR900", "variant": "base",
    "must_mention": ["a", "b", "c"], "must_not": [{"action": "x", "severity": "severe"}],
    "urgency_target": "emergency", "antibiotic_target": "indicated",
}
OTHER = dict(CASE, case_id="CR901-BASE", anchor_id="CR901")


def test_hand_computed_kappa_and_ac1():
    a, b = [1, 1, 0, 0], [1, 0, 0, 0]
    assert observed_agreement(a, b) == 0.75
    assert cohen_kappa(a, b, (0, 1)) == pytest.approx(0.5)
    assert gwet_ac1(a, b, (0, 1)) == pytest.approx(0.28125 / 0.53125)


def test_ac1_stays_high_when_kappa_collapses_on_a_rare_category():
    a = [False] * 19 + [True]
    b = [False] * 20
    assert observed_agreement(a, b) == 0.95
    assert cohen_kappa(a, b, BINARY) == pytest.approx(0.0)
    assert gwet_ac1(a, b, BINARY) > 0.9


def test_undefined_values():
    assert cohen_kappa([1, 1], [1, 1], (0, 1)) is None
    assert gwet_ac1([1, 1], [1, 1], (0, 1)) == 1.0
    assert cohen_kappa([], [], (0, 1)) is None and gwet_ac1([], [], (0, 1)) is None


def test_perfect_disagreement_is_negative():
    assert cohen_kappa([0, 1, 0, 1], [1, 0, 1, 0], (0, 1)) == pytest.approx(-1.0)


def ann(case, run="r1", **fields):
    return {"case_id": case["case_id"], "model_id": "m", "run_id": run, **fields}


def test_table_compares_decisions_ratings_and_each_rubric_item():
    first = [
        ann(CASE, urgency="emergency", antibiotics_prescribed=True, red_flags_mentioned=[0, 1],
            ratings={"diagnostic_reasoning": 2, "uncertainty": None}),
        ann(OTHER, urgency="urgent", red_flags_mentioned=[2]),
        ann(CASE, run="r9", urgency="routine"),  # not annotated by the second rater
    ]
    second = [
        ann(CASE, urgency="emergency", antibiotics_prescribed=False, red_flags_mentioned=[0],
            ratings={"diagnostic_reasoning": 1, "uncertainty": 2}),
        ann(OTHER, urgency="urgent", red_flags_mentioned=[2]),
    ]
    rows = {r["field"]: r for r in agreement_table([CASE, OTHER], first, second)}
    assert rows["urgency"]["n"] == 2 and rows["urgency"]["agreement"] == 1.0
    assert rows["antibiotics_prescribed"]["n"] == 1 and rows["antibiotics_prescribed"]["agreement"] == 0.0
    assert rows["red_flags_mentioned"]["n"] == 6
    assert rows["red_flags_mentioned"]["agreement"] == pytest.approx(5 / 6)
    assert rows["ratings.diagnostic_reasoning"]["n"] == 1
    assert "ratings.uncertainty" not in rows  # N/A on one side is not compared
    assert matched_responses(first, second) == 2


def test_format_agreement_prints_a_row_per_field():
    rows = agreement_table([CASE], [ann(CASE, urgency="urgent")], [ann(CASE, urgency="urgent")])
    text = format_agreement(rows, 1, "judge.jsonl", "human.jsonl")
    assert "judge.jsonl x human.jsonl: 1 matched" in text
    assert "| urgency | 1 | 1.00 | n/a | 1.00 |" in text
