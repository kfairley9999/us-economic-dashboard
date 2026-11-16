"""Pure, side-effect-free transforms on FRED time series.

Every function takes and returns ``pandas`` objects indexed by a
``DatetimeIndex`` so it can be unit-tested without touching the network.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

SAHM_THRESHOLD = 0.50  # percentage points


def _calendar(s: pd.Series) -> str | None:
    """Regular pandas frequency for a monthly or quarterly series, else None."""
    if len(s) < 3:
        return None
    step = pd.Series(s.index).diff().dt.days.median()
    if 27 <= step <= 32:
        return "MS"
    if 88 <= step <= 93:
        return "QS-JAN"
    return None


def fill_single_gaps(s: pd.Series) -> pd.Series:
    """Regular calendar with isolated missing periods filled log-linearly.

    Only interior gaps of one period are filled (geometric mean of the
    neighbours); longer gaps stay missing. Non-positive series are filled
    linearly instead.
    """
    freq = _calendar(s)
    if freq is None:
        return s
    reg = s.asfreq(freq)
    if (s > 0).all():
        filled = np.exp(np.log(reg).interpolate(limit=1, limit_area="inside"))
    else:
        filled = reg.interpolate(limit=1, limit_area="inside")
    # interpolate(limit=1) would also part-fill longer runs; keep only lone gaps.
    lone = reg.isna() & reg.shift(1).notna() & reg.shift(-1).notna()
    return reg.where(~lone, filled)


def missing_periods(s: pd.Series, since: str | None = None) -> list[pd.Timestamp]:
    """Interior months/quarters with no observation (e.g. cancelled releases)."""
    freq = _calendar(s)
    if freq is None:
        return []
    reg = s.asfreq(freq)
    gaps = reg.index[reg.isna()]
    if since:
        gaps = gaps[gaps >= pd.Timestamp(since)]
    return list(gaps)


def _lagged(s: pd.Series, offset: pd.DateOffset) -> pd.Series:
    """Value observed ``offset`` earlier, aligned to ``s``'s dates.

    Lags are matched on the calendar, not by row position. A row-based
    ``shift(12)`` would silently compare against the wrong month whenever a
    release is missing (e.g. October 2025, when the federal shutdown cancelled
    the CPI and household-survey collections). An isolated missing *base*
    period is interpolated with :func:`fill_single_gaps`; the missing period
    itself never gets a value.
    """
    base = fill_single_gaps(s)
    prev = base.reindex(s.index - offset)
    prev.index = s.index
    return prev


def yoy_pct(s: pd.Series) -> pd.Series:
    """Year-over-year percent change, matched on the calendar date."""
    return (s / _lagged(s, pd.DateOffset(years=1)) - 1.0) * 100.0


def annualized_pct(s: pd.Series, months: int) -> pd.Series:
    """Compound-annualized growth over the past ``months`` months.

    ``annualized_pct(gdp, 3)`` is the headline quarter-over-quarter SAAR real
    GDP growth rate; ``annualized_pct(core_cpi, 3)`` is 3-month annualized
    core inflation.
    """
    ratio = s / _lagged(s, pd.DateOffset(months=months))
    return (ratio ** (12 / months) - 1.0) * 100.0


def monthly_change(s: pd.Series) -> pd.Series:
    """Change from the previous calendar month (e.g. payroll job gains)."""
    return s - _lagged(s, pd.DateOffset(months=1))


def sahm_rule(unrate: pd.Series) -> pd.Series:
    """Real-time Sahm rule recession indicator (percentage points).

    Three-month moving average of the unemployment rate minus the minimum of
    that average over the *preceding* 12 months. A reading of 0.50 pp or more
    has historically signalled the early months of a recession.

    The series is put on a regular monthly calendar first; a window tolerates
    one missing month (2 of 3 months for the average, 10 of 12 for the prior
    minimum) so a single skipped release does not break the indicator.
    """
    m = unrate.asfreq("MS")
    ma3 = m.rolling(3, min_periods=2).mean()
    prior_min = ma3.shift(1).rolling(12, min_periods=10).min()
    out = ma3 - prior_min
    return out.reindex(unrate.index)


def spread(long: pd.Series, short: pd.Series) -> pd.Series:
    """Long minus short yield on matching dates (rows with a gap are dropped)."""
    df = pd.concat({"long": long, "short": short}, axis=1).dropna()
    return df["long"] - df["short"]


@dataclass(frozen=True)
class Episode:
    start: pd.Timestamp
    end: pd.Timestamp
    ongoing: bool

    @property
    def days(self) -> int:
        return int((self.end - self.start).days) + 1


def _runs(mask: pd.Series) -> list[Episode]:
    """Contiguous True runs in a boolean series, as inclusive date ranges."""
    mask = mask.astype(bool)
    episodes: list[Episode] = []
    if mask.empty:
        return episodes
    group = (mask != mask.shift()).cumsum()
    for _, run in mask.groupby(group):
        if run.iloc[0]:
            episodes.append(Episode(run.index[0], run.index[-1], ongoing=run.index[-1] == mask.index[-1]))
    return episodes


def inversion_episodes(spread_s: pd.Series, min_days: int = 1) -> list[Episode]:
    """Periods where the yield-curve spread was below zero.

    ``min_days`` filters out one-off blips (calendar days from first to last
    inverted observation, inclusive).
    """
    return [e for e in _runs(spread_s.dropna() < 0) if e.days >= min_days]


def recession_periods(usrec: pd.Series) -> list[tuple[str, str]]:
    """NBER recession months as ``(first_month, last_month)`` ``YYYY-MM`` pairs."""
    return [(e.start.strftime("%Y-%m"), e.end.strftime("%Y-%m")) for e in _runs(usrec.dropna() > 0.5)]


def value_as_of(s: pd.Series, offset: pd.DateOffset) -> tuple[pd.Timestamp, float] | None:
    """Most recent observation on or before ``last date - offset``."""
    s = s.dropna()
    if s.empty:
        return None
    target = s.index[-1] - offset
    past = s.loc[:target]
    if past.empty:
        return None
    return past.index[-1], float(past.iloc[-1])


def thin_daily(s: pd.Series, full_res_days: int = 730) -> pd.Series:
    """Keep the last ``full_res_days`` at daily resolution; older history weekly.

    Weekly points are the last observation of each Friday-ending week, which
    keeps multi-decade charts light without visibly changing their shape.
    """
    s = s.dropna()
    if s.empty:
        return s
    cutoff = s.index[-1] - pd.Timedelta(days=full_res_days)
    old = s.loc[s.index < cutoff]
    recent = s.loc[s.index >= cutoff]
    if not old.empty:
        weekly = old.groupby(old.index.to_period("W-FRI")).tail(1)
        old = weekly
    return pd.concat([old, recent])


def clean_number(x: float | None, decimals: int) -> float | None:
    """Round for JSON; map NaN/inf to ``None`` so the output is valid JSON."""
    if x is None:
        return None
    x = float(x)
    if math.isnan(x) or math.isinf(x):
        return None
    r = round(x, decimals)
    return 0.0 if r == 0 else r  # avoid "-0.0"
