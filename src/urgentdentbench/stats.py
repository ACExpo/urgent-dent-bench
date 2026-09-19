from __future__ import annotations
import numpy as np
import pandas as pd

def paired_cluster_bootstrap(
    df: pd.DataFrame,
    score_a: str,
    score_b: str,
    cluster_col: str = "anchor_id",
    n_boot: int = 5000,
    seed: int = 2026,
):
    """Paired bootstrap of mean score difference, resampling anchor clusters."""
    work = df.dropna(subset=[score_a, score_b, cluster_col]).copy()
    clusters = work[cluster_col].unique()
    if len(clusters) < 2:
        raise ValueError("Need at least two clusters.")
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(n_boot):
        sampled = rng.choice(clusters, size=len(clusters), replace=True)
        pieces = [work[work[cluster_col] == c] for c in sampled]
        boot = pd.concat(pieces, ignore_index=True)
        diffs.append((boot[score_a] - boot[score_b]).mean())
    diffs = np.asarray(diffs)
    return {
        "mean_difference": float((work[score_a] - work[score_b]).mean()),
        "ci_2_5": float(np.quantile(diffs, 0.025)),
        "ci_97_5": float(np.quantile(diffs, 0.975)),
    }
