import csv
import json
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def dataset_copy(tmp_path):
    """Exercise the real CLI against disposable shards, never the checked-in data."""
    root = tmp_path / "repo"
    shutil.copytree(ROOT / "data/benchmark", root / "data/benchmark")
    (root / "scripts").mkdir()
    shutil.copyfile(ROOT / "scripts/validate_dataset.py", root / "scripts/validate_dataset.py")
    return root


def run_validator(root):
    return subprocess.run(
        [sys.executable, str(root / "scripts/validate_dataset.py")],
        cwd=root.parent,
        capture_output=True,
        text=True,
        timeout=20,
    )


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def write_rows(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_validator_finds_shards_outside_repository():
    result = run_validator(ROOT)
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("OK\nrecords: 110\n")


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_type", "unknown"),
        ("variant", "counterfactul"),
        ("vignette", ["not a string"]),
        ("reference_management", [123]),
        ("case_id", ""),
        ("vignette", ""),
    ],
)
def test_validator_rejects_invalid_record(dataset_copy, field, value):
    path = sorted((dataset_copy / "data/benchmark/cases").glob("*.jsonl"))[0]
    rows = read_rows(path)
    rows[0][field] = value
    write_rows(path, rows)
    result = run_validator(dataset_copy)
    assert result.returncode != 0, result.stdout
    assert path.name in result.stderr
    assert not result.stdout.startswith("OK")


def test_validator_rejects_missing_required_field_before_reporting_success(dataset_copy):
    path = sorted((dataset_copy / "data/benchmark/cases").glob("*.jsonl"))[0]
    rows = read_rows(path)
    del rows[0]["domain"]
    write_rows(path, rows)
    result = run_validator(dataset_copy)
    assert result.returncode != 0
    assert "domain" in result.stderr
    assert not result.stdout.startswith("OK")


def test_validator_rejects_duplicate_ids_across_shards(dataset_copy):
    first, second, *_ = sorted((dataset_copy / "data/benchmark/cases").glob("*.jsonl"))
    rows = read_rows(second)
    rows[0]["case_id"] = read_rows(first)[0]["case_id"]
    write_rows(second, rows)
    result = run_validator(dataset_copy)
    assert result.returncode != 0
    assert "Duplicate case IDs" in result.stderr


@pytest.mark.parametrize("extra_row", [False, True], ids=["109-rows", "111-rows"])
def test_validator_rejects_wrong_case_count(dataset_copy, extra_row):
    path = sorted((dataset_copy / "data/benchmark/cases").glob("*.jsonl"))[0]
    rows = read_rows(path)
    if extra_row:
        rows.append(dict(rows[0], case_id="EXTRA"))
    else:
        rows.pop()
    write_rows(path, rows)
    result = run_validator(dataset_copy)
    assert result.returncode != 0
    assert "Expected 110 rows" in result.stderr


def test_validator_rejects_missing_shards(dataset_copy):
    for path in (dataset_copy / "data/benchmark/cases").glob("*.jsonl"):
        path.unlink()
    result = run_validator(dataset_copy)
    assert result.returncode != 0
    assert "No benchmark case shards found" in result.stderr


def test_committed_cases_preserve_anchor_triplets_and_controls():
    rows = [
        row
        for path in sorted((ROOT / "data/benchmark/cases").glob("*.jsonl"))
        for row in read_rows(path)
    ]
    with (ROOT / "data/anchors/source_manifest.csv").open(encoding="utf-8", newline="") as f:
        anchors = {row["anchor_id"] for row in csv.DictReader(f)}
    groups = defaultdict(Counter)
    for row in rows:
        if row["source_type"] == "case_report_derived":
            groups[row["anchor_id"]][row["variant"]] += 1
        else:
            assert row["source_type"] == row["variant"] == "guideline_control"
            assert row["anchor_id"] is None
    assert len(anchors) == 30
    assert set(groups) == anchors
    for anchor, variants in groups.items():
        assert variants == {"base": 1, "missing_critical": 1, "counterfactual": 1}, anchor
    assert sum(row["source_type"] == "guideline_control" for row in rows) == 20
