import pandas as pd
import pytest

from urgentdentbench.stats import paired_cluster_bootstrap


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
