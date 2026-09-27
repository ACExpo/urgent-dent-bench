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


def cluster_bootstrap_ci(values, clusters, n_boot: int = 2000, seed: int = 2026, level: float = 0.95):
    """Mean of ``values`` with a percentile bootstrap CI that resamples whole clusters.

    ``values`` may contain None (not annotated), which is dropped with its
    cluster label; booleans count as 0/1. The interval is None when fewer than
    two clusters remain.
    """
    pairs = [(float(v), c) for v, c in zip(values, clusters) if v is not None]
    if not pairs:
        return {"value": None, "lo": None, "hi": None, "n": 0}
    labels = sorted({c for _, c in pairs}, key=str)
    position = {c: i for i, c in enumerate(labels)}
    sums = np.zeros(len(labels))
    counts = np.zeros(len(labels))
    for value, cluster in pairs:
        sums[position[cluster]] += value
        counts[position[cluster]] += 1
    mean = float(sums.sum() / counts.sum())
    if len(labels) < 2:
        return {"value": mean, "lo": None, "hi": None, "n": len(pairs)}
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(labels), size=(n_boot, len(labels)))
    boot = sums[idx].sum(axis=1) / counts[idx].sum(axis=1)
    tail = (1 - level) / 2
    return {
        "value": mean,
        "lo": float(np.quantile(boot, tail)),
        "hi": float(np.quantile(boot, 1 - tail)),
        "n": len(pairs),
    }
