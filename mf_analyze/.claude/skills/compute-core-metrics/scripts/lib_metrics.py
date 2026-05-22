"""Pure-function metric implementations for compute-core-metrics.

Each function takes a clean pandas Series/DataFrame and returns a number (or a
small dict/tuple). No file I/O, no globals — testable in isolation.

Conventions (see references/formula_choices.md for rationale):
- Returns are monthly unless otherwise noted.
- Annualization factor is 12 (monthly → annual).
- Risk-free rate is annualized (decimal, e.g. 0.07 = 7%).
- Returns expressed as decimals throughout (0.45 = 45%).
"""

from __future__ import annotations

from datetime import date
from typing import Optional

import numpy as np
import pandas as pd

MONTHS_PER_YEAR = 12


# -------------------------------------------------------------------- returns

def nav_to_monthly_returns(nav: pd.DataFrame, nav_col: str = "nav") -> pd.Series:
    """Convert a daily NAV DataFrame (columns: date, nav) into monthly returns.

    Returns a Series indexed by month-end (Timestamp), values are pct_change.
    The first month is NaN (no prior price).
    """
    df = nav.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    # "ME" = month-end. Take the last available NAV in each month.
    monthly = df[nav_col].resample("ME").last()
    return monthly.pct_change().dropna()


def tri_to_monthly_returns(tri: pd.DataFrame, value_col: str = "value") -> pd.Series:
    """Convert a daily TRI DataFrame (columns: date, value) into monthly returns."""
    return nav_to_monthly_returns(tri.rename(columns={value_col: "nav"}))


def align_monthly(fund: pd.Series, bench: pd.Series) -> pd.DataFrame:
    """Inner-join two monthly-returns Series into a DataFrame [fund, bench]."""
    df = pd.concat([fund.rename("fund"), bench.rename("bench")], axis=1)
    return df.dropna()


# --------------------------------------------------------------------- Sortino

def sortino_ratio(
    monthly_returns: pd.Series,
    risk_free_annual: float = 0.07,
    periods_per_year: int = MONTHS_PER_YEAR,
) -> float:
    """Annualized Sortino ratio.

    Uses target = risk-free rate. Downside std is computed only on months
    where the return fell below the per-period risk-free rate.
    """
    if len(monthly_returns) < 6:
        return float("nan")
    target_period = (1 + risk_free_annual) ** (1 / periods_per_year) - 1
    excess = monthly_returns - target_period
    # Downside deviation: std of negative excess returns, treated as zero otherwise.
    downside_sq = np.where(excess < 0, excess**2, 0.0)
    downside_dev = np.sqrt(downside_sq.mean())
    if downside_dev == 0 or np.isnan(downside_dev):
        return float("nan")
    annualized_excess = excess.mean() * periods_per_year
    return float(annualized_excess / (downside_dev * np.sqrt(periods_per_year)))


# --------------------------------------------------------------------- Drawdown

def max_drawdown_and_recovery(nav: pd.DataFrame, nav_col: str = "nav") -> dict:
    """Compute max drawdown using daily NAV (not monthly).

    Returns dict with:
        mdd_pct          drawdown depth as a negative decimal (e.g. -0.32)
        peak_date        ISO date of the prior peak
        trough_date      ISO date of the trough
        recovery_date    ISO date when NAV crossed back above peak, or None
        recovery_months  months from trough to recovery, or None
    """
    df = nav.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    series = df[nav_col]

    running_max = series.cummax()
    drawdown = series / running_max - 1.0
    if drawdown.empty:
        return _empty_dd_result()

    trough_date = drawdown.idxmin()
    mdd = float(drawdown.loc[trough_date])
    peak_value = running_max.loc[trough_date]
    # Peak date = last day on which running_max increased to peak_value before the trough.
    pre_trough = series.loc[:trough_date]
    peak_date = pre_trough[pre_trough == peak_value].index.min()

    # Recovery = first date after trough where NAV >= peak value.
    post_trough = series.loc[trough_date:]
    recovered = post_trough[post_trough >= peak_value]
    if recovered.empty:
        recovery_date = None
        recovery_months: Optional[float] = None
    else:
        recovery_date = recovered.index.min()
        recovery_months = round((recovery_date - trough_date).days / 30.4375, 1)

    return {
        "mdd_pct": round(mdd, 4),
        "peak_date": peak_date.date().isoformat() if peak_date is not None else None,
        "trough_date": trough_date.date().isoformat(),
        "recovery_date": recovery_date.date().isoformat() if recovery_date else None,
        "recovery_months": recovery_months,
    }


def _empty_dd_result() -> dict:
    return {
        "mdd_pct": float("nan"),
        "peak_date": None,
        "trough_date": None,
        "recovery_date": None,
        "recovery_months": None,
    }


# ---------------------------------------------------------- rolling 3Y windows

def rolling_3y_alpha_and_beat(
    aligned: pd.DataFrame,
    window_months: int = 36,
) -> dict:
    """Monthly-stepped 3Y windows. Returns median alpha, recent alpha, beat-%.

    Alpha = (fund 3Y CAGR) - (bench 3Y CAGR). Annualized decimal.

    `aligned` must have columns ['fund', 'bench'] of monthly returns.
    Requires at least `window_months` rows.
    """
    if len(aligned) < window_months:
        return {
            "rolling_alpha_3y_median": float("nan"),
            "rolling_alpha_3y_recent": float("nan"),
            "beat_pct_3y": float("nan"),
            "n_windows": 0,
        }
    # Cumulative-product growth factor; CAGR over each 36-month window.
    n = len(aligned)
    n_windows = n - window_months + 1
    fund_returns = aligned["fund"].values
    bench_returns = aligned["bench"].values

    alphas = np.empty(n_windows, dtype=float)
    wins = 0
    for i in range(n_windows):
        f_growth = np.prod(1.0 + fund_returns[i : i + window_months])
        b_growth = np.prod(1.0 + bench_returns[i : i + window_months])
        # CAGR over 36 months = growth^(12/36) - 1 = growth^(1/3) - 1
        f_cagr = f_growth ** (MONTHS_PER_YEAR / window_months) - 1
        b_cagr = b_growth ** (MONTHS_PER_YEAR / window_months) - 1
        alphas[i] = f_cagr - b_cagr
        if f_cagr > b_cagr:
            wins += 1

    return {
        "rolling_alpha_3y_median": float(np.median(alphas)),
        "rolling_alpha_3y_recent": float(alphas[-1]),
        "beat_pct_3y": wins / n_windows,
        "n_windows": n_windows,
    }


# -------------------------------------------------------------- Capture & beta

def downside_capture(aligned: pd.DataFrame) -> float:
    """Morningstar-style downside capture ratio.

    = sum(R_fund | R_bench < 0) / sum(R_bench | R_bench < 0)

    Below 1.0 = fund absorbed less of the benchmark's downside. Above 1.0 = worse.
    Returns NaN if benchmark never declined in the period.
    """
    down = aligned[aligned["bench"] < 0]
    if len(down) < 3:
        return float("nan")
    num = down["fund"].sum()
    den = down["bench"].sum()
    if den == 0:
        return float("nan")
    return float(num / den)


def beta(aligned: pd.DataFrame) -> float:
    """OLS-style beta = cov(R_fund, R_bench) / var(R_bench)."""
    if len(aligned) < 12:
        return float("nan")
    bench_var = aligned["bench"].var()
    if bench_var == 0:
        return float("nan")
    return float(aligned[["fund", "bench"]].cov().iloc[0, 1] / bench_var)


# --------------------------------------------------------------- Lookback clip

def clamp_to_recent_years(monthly: pd.Series, years: float) -> pd.Series:
    """Return the trailing `years` of a monthly-indexed Series."""
    if monthly.empty:
        return monthly
    cutoff = monthly.index.max() - pd.DateOffset(years=int(years))
    return monthly.loc[monthly.index >= cutoff]


def clamp_aligned_to_recent_years(aligned: pd.DataFrame, years: float) -> pd.DataFrame:
    if aligned.empty:
        return aligned
    cutoff = aligned.index.max() - pd.DateOffset(years=int(years))
    return aligned.loc[aligned.index >= cutoff]


# ---------------------------------------------------------------- Fund summary

def fund_age_years(nav: pd.DataFrame) -> float:
    """Years of NAV history available."""
    if nav.empty:
        return 0.0
    df = nav.copy()
    df["date"] = pd.to_datetime(df["date"])
    span = df["date"].max() - df["date"].min()
    return round(span.days / 365.25, 1)


def compute_all_metrics(
    nav: pd.DataFrame,
    tri: pd.DataFrame,
    risk_free_annual: float = 0.07,
    sortino_lookback_years: int = 5,
    rolling_lookback_years: int = 7,
    capture_lookback_years: int = 5,
    beta_lookback_years: int = 5,
) -> dict:
    """Top-level: compute the full per-fund metric row.

    `nav` columns: date, nav
    `tri` columns: date, value
    """
    warnings: list[str] = []
    age = fund_age_years(nav)

    fund_monthly = nav_to_monthly_returns(nav)
    bench_monthly = tri_to_monthly_returns(tri)
    aligned_full = align_monthly(fund_monthly, bench_monthly)

    if len(aligned_full) < 12:
        warnings.append(f"too_few_aligned_months_{len(aligned_full)}")
        return {
            "sortino_5y": float("nan"),
            "rolling_alpha_3y_median": float("nan"),
            "rolling_alpha_3y_recent": float("nan"),
            "beat_pct_3y": float("nan"),
            "n_rolling_windows": 0,
            "max_drawdown_pct": float("nan"),
            "max_drawdown_date": None,
            "recovery_months": None,
            "downside_capture_5y": float("nan"),
            "beta_5y": float("nan"),
            "fund_age_years": age,
            "lookback_warnings": ";".join(warnings),
        }

    # Sortino — 5Y window on monthly fund returns
    sortino_window = clamp_to_recent_years(fund_monthly, sortino_lookback_years)
    if age < sortino_lookback_years:
        warnings.append(f"sortino_used_{age}y_(<{sortino_lookback_years}y)")
    sortino = sortino_ratio(sortino_window, risk_free_annual=risk_free_annual)

    # Rolling alpha + beat-% — 7Y window on aligned monthly returns
    rolling_window = clamp_aligned_to_recent_years(aligned_full, rolling_lookback_years)
    if len(rolling_window) < 36:
        warnings.append("rolling_alpha_skipped_<3y_aligned")
    rolling = rolling_3y_alpha_and_beat(rolling_window)

    # Max drawdown — all available daily NAV
    dd = max_drawdown_and_recovery(nav)

    # Downside capture — 5Y aligned
    capture_window = clamp_aligned_to_recent_years(aligned_full, capture_lookback_years)
    capture = downside_capture(capture_window)
    if age < capture_lookback_years:
        warnings.append(f"capture_used_{age}y_(<{capture_lookback_years}y)")

    # Beta — 5Y aligned
    beta_window = clamp_aligned_to_recent_years(aligned_full, beta_lookback_years)
    b = beta(beta_window)

    return {
        "sortino_5y": round(sortino, 3) if not np.isnan(sortino) else float("nan"),
        "rolling_alpha_3y_median": round(rolling["rolling_alpha_3y_median"], 4),
        "rolling_alpha_3y_recent": round(rolling["rolling_alpha_3y_recent"], 4),
        "beat_pct_3y": round(rolling["beat_pct_3y"], 3) if rolling["n_windows"] else float("nan"),
        "n_rolling_windows": rolling["n_windows"],
        "max_drawdown_pct": dd["mdd_pct"],
        "max_drawdown_date": dd["trough_date"],
        "recovery_months": dd["recovery_months"],
        "downside_capture_5y": round(capture, 3) if not np.isnan(capture) else float("nan"),
        "beta_5y": round(b, 3) if not np.isnan(b) else float("nan"),
        "fund_age_years": age,
        "lookback_warnings": ";".join(warnings),
    }
