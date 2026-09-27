import json

from urgentdentbench.report import build_report, format_csv, format_json, format_markdown

BASE = {"case_id": "CR900-BASE", "anchor_id": "CR900", "variant": "base", "must_mention": ["a", "b"],
        "must_not": [{"action": "x", "severity": "severe"}], "urgency_target": "emergency",
        "antibiotic_target": "indicated"}
CF = {"case_id": "CR900-CF", "anchor_id": "CR900", "variant": "counterfactual", "must_mention": ["a"],
      "must_not": [{"action": "w", "severity": "minor"}], "urgency_target": "urgent", "antibiotic_target": "indicated",
      "expected_change": {"urgency": "emergency->urgent", "key_decision": "k"}}
BASE2 = dict(BASE, case_id="CR901-BASE", anchor_id="CR901")
GC = {"case_id": "GC900", "anchor_id": None, "variant": "guideline_control", "must_mention": ["a"],
      "must_not": [{"action": "v", "severity": "minor"}], "urgency_target": "routine",
      "antibiotic_target": "not_applicable"}
CASES = [BASE, CF, BASE2, GC]


def ann(case, model="m1", run="r1", **fields):
    return {"case_id": case["case_id"], "model_id": model, "run_id": run, **fields}


ANNOTATIONS = [
    ann(BASE, urgency="emergency", dangerous_actions=[]),
    ann(CF, urgency="urgent", dangerous_actions=[]),
    ann(BASE2, urgency="urgent", dangerous_actions=[0]),
    ann(GC, urgency="routine", dangerous_actions=[]),
    ann(BASE, run="r2", urgency="urgent", dangerous_actions=[]),
    ann(GC, model="m2", urgency="emergency", dangerous_actions=[0]),
]


def test_report_gives_each_system_every_metric_with_intervals():
    report = build_report(CASES, ANNOTATIONS, n_boot=300)
    assert list(report) == ["m1", "m2"]
    m1 = report["m1"]
    assert m1["Dangerous-action rate"]["value"] == 0.2 and m1["Dangerous-action rate"]["n"] == 5
    assert m1["Disposition accuracy"]["value"] == 0.6
    assert m1["Dangerous-action rate"]["lo"] <= 0.2 <= m1["Dangerous-action rate"]["hi"]
    assert m1["Counterfactual sensitivity"] == {"value": 1.0, "lo": None, "hi": None, "n": 1}
    assert m1["Consistency: urgency"] == {"value": 0.5, "lo": None, "hi": None, "n": 1}
    assert m1["CSCS 1.1"]["value"] is None
    assert report["m2"]["Dangerous-action rate"]["value"] == 1.0


def test_report_is_reproducible_for_a_seed():
    first = build_report(CASES, ANNOTATIONS, n_boot=300, seed=5)
    assert first == build_report(CASES, ANNOTATIONS, n_boot=300, seed=5)


def test_markdown_lists_metrics_as_rows_and_systems_as_columns():
    text = format_markdown(build_report(CASES, ANNOTATIONS, n_boot=300))
    lines = text.splitlines()
    assert lines[0] == "| Metric | m1 | m2 |"
    labels = [line.split(" | ")[0].lstrip("| ") for line in lines[2:] if line.startswith("|")]
    assert labels.index("Counterfactual sensitivity") < labels.index("Consistency: urgency")
    assert "| CSCS 1.1 | – | – |" in text
    assert "0.20 [" in text and "(n=5)" in text


def test_csv_and_json_formats():
    report = build_report(CASES, ANNOTATIONS, n_boot=300)
    rows = format_csv(report).splitlines()
    assert rows[0] == "system,metric,value,ci_low,ci_high,n"
    assert len(rows) == 1 + 2 * len(report["m1"])
    assert json.loads(format_json(report))["m2"]["Dangerous-action rate"]["value"] == 1.0
