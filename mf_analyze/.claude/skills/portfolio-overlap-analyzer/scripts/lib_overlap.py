"""Pure-function similarity metrics for portfolio-overlap-analyzer.

Each function takes clean dicts / pandas Series and returns a number.
No I/O, no globals — testable in isolation.
"""

from __future__ import annotations

import math
import numpy as np
import pandas as pd


# --------------------------------------------------------------- Stock overlap

def weighted_jaccard(weights_a: dict[str, float], weights_b: dict[str, float]) -> float:
    """Weighted Jaccard similarity over two {key: weight} dicts.

    sim = Σ min(w_a, w_b) / Σ max(w_a, w_b)

    Returns NaN if either dict is empty or both unions sum to zero.
    """
    if not weights_a or not weights_b:
        return float("nan")
    keys = set(weights_a) | set(weights_b)
    num, den = 0.0, 0.0
    for k in keys:
        wa = weights_a.get(k, 0.0) or 0.0
        wb = weights_b.get(k, 0.0) or 0.0
        num += min(wa, wb)
        den += max(wa, wb)
    if den == 0:
        return float("nan")
    return num / den


# --------------------------------------------------------------- Sector cosine

def cosine_similarity(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
    """Cosine similarity over two sparse {key: value} dicts.

    Returns NaN if either vector has zero magnitude.
    """
    if not vec_a or not vec_b:
        return float("nan")
    keys = set(vec_a) | set(vec_b)
    dot = sum((vec_a.get(k, 0.0) or 0.0) * (vec_b.get(k, 0.0) or 0.0) for k in keys)
    mag_a = math.sqrt(sum((v or 0.0) ** 2 for v in vec_a.values()))
    mag_b = math.sqrt(sum((v or 0.0) ** 2 for v in vec_b.values()))
    if mag_a == 0 or mag_b == 0:
        return float("nan")
    return dot / (mag_a * mag_b)


# ---------------------------------------------------------- Return correlation

def monthly_returns(nav: pd.DataFrame, nav_col: str = "nav") -> pd.Series:
    """Convert daily NAV (date, nav) → monthly pct_change indexed by month-end."""
    df = nav.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    return df[nav_col].resample("ME").last().pct_change().dropna()


def correlation_matrix(
    returns_by_id: dict[str, pd.Series],
    min_overlap_months: int = 24,
) -> pd.DataFrame:
    """Pearson correlation matrix over a dict of monthly-return Series.

    Pairs with fewer than `min_overlap_months` aligned observations are emitted as NaN.
    """
    ids = sorted(returns_by_id)
    if not ids:
        return pd.DataFrame()
    df = pd.concat(
        [returns_by_id[i].rename(i) for i in ids], axis=1, join="outer"
    )
    matrix = pd.DataFrame(np.nan, index=ids, columns=ids, dtype=float)
    for i in ids:
        for j in ids:
            if i == j:
                matrix.loc[i, j] = 1.0
                continue
            pair = df[[i, j]].dropna()
            if len(pair) < min_overlap_months:
                continue
            matrix.loc[i, j] = pair[i].corr(pair[j])
    return matrix


# ----------------------------------------------------------- Redundancy combo

def redundancy_score(stock_jaccard: float, sector_cosine: float, return_corr: float) -> float:
    """Simple average of the three signals (return-corr floored at 0). Bounded [0, 1]."""
    parts = []
    for x in (stock_jaccard, sector_cosine, max(return_corr, 0.0) if return_corr == return_corr else float("nan")):
        if x == x:  # not NaN
            parts.append(x)
    if not parts:
        return float("nan")
    return sum(parts) / len(parts)


def is_redundant(
    stock_jaccard: float,
    sector_cosine: float,
    return_corr: float,
    *,
    min_stock: float = 0.30,
    min_sector: float = 0.85,
    min_corr: float = 0.90,
) -> bool:
    """Conjunction-of-thresholds redundancy flag. See references/redundancy_thresholds.md."""
    if any(x != x for x in (stock_jaccard, sector_cosine, return_corr)):
        return False
    return (
        stock_jaccard >= min_stock
        and sector_cosine >= min_sector
        and return_corr >= min_corr
    )
