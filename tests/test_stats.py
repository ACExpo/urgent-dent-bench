import pandas as pd
import pytest

from urgentdentbench.stats import cluster_bootstrap_ci, paired_cluster_bootstrap


def scores(rows):
    return pd.DataFrame(rows, columns=["case_id", "anchor_id", "model_a", "model_b"])


def test_guideline_controls_without_anchor_are_kept_as_their_own_clusters():
    df = scores([
        ("CR001-BASE", "CR001", 1.0, 1.0),
        ("CR001-CF", "CR001", 1.0, 1.0),
        ("CR002-BASE", "CR002", 1.0, 1.0),
        ("GC001", None, 1.0, 0.0),
        ("GC002", None, 1.0, 0.0),
    ])
    result = paired_cluster_bootstrap(df, "model_a", "model_b", n_boot=200)
    assert result["mean_difference"] == pytest.approx(2 / 5)
    assert result["ci_97_5"] > 0


def test_controls_alone_form_enough_clusters():
    df = scores([("GC001", None, 1.0, 0.0), ("GC002", None, 0.0, 0.0)])
    result = paired_cluster_bootstrap(df, "model_a", "model_b", n_boot=200)
    assert result["mean_difference"] == pytest.approx(0.5)


def test_rows_without_any_cluster_id_are_rejected():
    df = scores([
        ("CR001-BASE", "CR001", 1.0, 0.0),
        ("CR002-BASE", "CR002", 1.0, 0.0),
        (None, None, 1.0, 0.0),
    ])
    with pytest.raises(ValueError, match="no cluster id"):
        paired_cluster_bootstrap(df, "model_a", "model_b", n_boot=10)


def test_cluster_bootstrap_ci_resamples_clusters_and_skips_missing_values():
    values = [1, 1, 0, 0, None, True, False]
    clusters = ["A", "A", "B", "B", "C", "GC1", "GC2"]
    result = cluster_bootstrap_ci(values, clusters, n_boot=500, seed=1)
    assert result["n"] == 6
    assert result["value"] == pytest.approx(0.5)
    assert 0 <= result["lo"] <= result["value"] <= result["hi"] <= 1
    assert result == cluster_bootstrap_ci(values, clusters, n_boot=500, seed=1)


def test_cluster_bootstrap_ci_keeps_clusters_together():
    # Resampling whole clusters can only give means of 0 (B, B), 3/4 (A, B) or 1 (A, A).
    result = cluster_bootstrap_ci([1, 1, 1, 0], ["A", "A", "A", "B"], n_boot=500, seed=3)
    assert result["value"] == pytest.approx(0.75)
    assert result["lo"] == 0.0 and result["hi"] == 1.0


def test_cluster_bootstrap_ci_without_enough_data():
    assert cluster_bootstrap_ci([None], ["A"]) == {"value": None, "lo": None, "hi": None, "n": 0}
    assert cluster_bootstrap_ci([1, 0], ["A", "A"]) == {"value": 0.5, "lo": None, "hi": None, "n": 2}
