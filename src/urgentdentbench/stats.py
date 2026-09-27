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
    fallback_col: str = "case_id",
):
    """Paired bootstrap of mean score difference, resampling anchor clusters.

    Rows without an anchor (guideline controls) are their own cluster, keyed by
    ``fallback_col``, so they stay in the analysis instead of being dropped.
    """
    work = df.dropna(subset=[score_a, score_b]).copy()
    cluster_ids = work[cluster_col]
    if fallback_col in work:
        cluster_ids = cluster_ids.fillna(work[fallback_col])
    if cluster_ids.isna().any():
        raise ValueError(f"Rows with no cluster id in {cluster_col!r} or {fallback_col!r}.")
    work[cluster_col] = cluster_ids
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
