import json

import pytest

from urgentdentbench.crosslingual import format_json, format_markdown, language_gap, paired_scores


def case(case_id, anchor, variant="base", **extra):
    return {"case_id": case_id, "anchor_id": anchor, "variant": variant, "must_mention": ["a", "b"],
            "must_not": [{"action": "x", "severity": "severe"}], "urgency_target": "emergency",
            "antibiotic_target": "indicated", **extra}


EN = [case("CR900-BASE", "CR900"), case("CR901-BASE", "CR901"), case("CR902-BASE", "CR902")]
PT = [dict(c, case_id=c["case_id"] + "-PT") for c in EN]
CASES = EN + PT
SYSTEM = "m/text/v1/t0"


def ann(case_id, dangerous, system=SYSTEM, run="r1", urgency="emergency"):
    portuguese = case_id.endswith("-PT")
    return {"case_id": case_id, "model_id": system + ("/pt-BR" if portuguese else ""), "run_id": run,
            "urgency": urgency, "dangerous_actions": [0] if dangerous else [], "red_flags_mentioned": [0, 1]}


ANNOTATIONS = [
    ann("CR900-BASE", False), ann("CR900-BASE-PT", True),
    ann("CR901-BASE", False), ann("CR901-BASE-PT", False, urgency="urgent"),
    ann("CR902-BASE", True), ann("CR902-BASE-PT", True),
    ann("CR900-BASE", False, run="r2"),  # no pt-BR answer for this run: not paired
]


def test_pairs_match_system_run_and_case_across_languages():
    pairs = paired_scores(CASES, ANNOTATIONS)
    assert list(pairs) == [SYSTEM]
    assert [(en["case_id"], pt["case_id"]) for en, pt in pairs[SYSTEM]] == [
        ("CR900-BASE", "CR900-BASE-PT"), ("CR901-BASE", "CR901-BASE-PT"), ("CR902-BASE", "CR902-BASE-PT")]


def test_gap_is_pt_minus_english_with_discordant_pairs():
    gap = language_gap(CASES, ANNOTATIONS, n_boot=300)[SYSTEM]
    dangerous = gap["Dangerous-action rate"]
    assert gap["pairs"] == 3
    assert dangerous["en"] == pytest.approx(1 / 3) and dangerous["pt"] == pytest.approx(2 / 3)
    assert dangerous["diff"] == pytest.approx(1 / 3) and dangerous["n"] == 3
    assert dangerous["lo"] <= dangerous["diff"] <= dangerous["hi"]
    assert gap["discordant_dangerous"] == {"en_only": 0, "pt_only": 1}
    assert gap["Disposition accuracy"]["diff"] == pytest.approx(-1 / 3)
    assert gap["Under-triage rate"]["diff"] == pytest.approx(1 / 3)
    assert gap["Red-flag recall"]["diff"] == 0


def test_metrics_without_annotations_on_both_sides_are_empty():
    gap = language_gap(CASES, ANNOTATIONS, n_boot=100)[SYSTEM]
    assert gap["CSCS 1.1"] == {"en": None, "pt": None, "diff": None, "lo": None, "hi": None, "n": 0}


def test_systems_are_kept_apart():
    other = [ann("CR900-BASE", True, system="other"), ann("CR900-BASE-PT", True, system=SYSTEM)]
    assert language_gap(CASES, other, n_boot=100) == {}


def test_formats():
    gap = language_gap(CASES, ANNOTATIONS, n_boot=300)
    text = format_markdown(gap)
    assert f"### {SYSTEM}" in text and "only in pt-BR: 1" in text
    assert "| Dangerous-action rate | 0.33 | 0.67 | 0.33 [" in text
    assert json.loads(format_json(gap))[SYSTEM]["pairs"] == 3
    assert "No response was annotated" in format_markdown({})
