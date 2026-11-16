"""Fetch FRED series, derive analytics, and write compact JSON for the site.

Usage::

    FRED_API_KEY=... python -m pipeline.build --out site/data

Two files are written:

* ``summary.json`` (a few KB): KPI cards, sparklines, recession signals, and
  metadata. The page renders above-the-fold content from this alone.
* ``series.json``: full chart histories in a columnar ``{"t": [...], "v": [...]}``
  layout, loaded right after.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from . import transforms as tf
from .series import SERIES

log = logging.getLogger("pipeline")

FRED_NOTICE = (
    "This product uses the FRED\u00ae API but is not endorsed or certified by the "
    "Federal Reserve Bank of St. Louis."
)
INFLATION_TARGET = 2.0
YEAR = pd.DateOffset(years=1)


# --------------------------------------------------------------------------- derive


def derive(raw: dict[str, pd.Series]) -> dict[str, pd.Series]:
    """All chart-ready series, keyed by the names the frontend uses."""
    spread = tf.spread(raw["DGS10"], raw["DGS2"])
    payroll_chg = tf.monthly_change(raw["PAYEMS"])
    return {
        "unrate": raw["UNRATE"],
        "sahm": tf.sahm_rule(raw["UNRATE"]).dropna(),
        "cpi_yoy": tf.yoy_pct(raw["CPIAUCSL"]).dropna(),
        "core_yoy": tf.yoy_pct(raw["CPILFESL"]).dropna(),
        "core_3m_ann": tf.annualized_pct(raw["CPILFESL"], 3).dropna(),
        "fedfunds": raw["FEDFUNDS"],
        "dgs10": raw["DGS10"],
        "dgs2": raw["DGS2"],
        "spread_10y2y": spread,
        "mortgage30": raw["MORTGAGE30US"],
        "gdp_saar": tf.annualized_pct(raw["GDPC1"], 3).dropna(),
        "gdp_yoy": tf.yoy_pct(raw["GDPC1"]).dropna(),
        "payrolls_chg": payroll_chg.dropna(),
        "payrolls_3mma": payroll_chg.asfreq("MS").rolling(3).mean().dropna(),
        "umcsent": raw["UMCSENT"],
    }


# Frequency and rounding per derived series (drives JSON size and labels).
SERIES_FMT: dict[str, tuple[str, int]] = {
    "unrate": ("M", 1),
    "sahm": ("M", 3),
    "cpi_yoy": ("M", 4),
    "core_yoy": ("M", 4),
    "core_3m_ann": ("M", 4),
    "fedfunds": ("M", 2),
    "dgs10": ("D", 2),
    "dgs2": ("D", 2),
    "spread_10y2y": ("D", 2),
    "mortgage30": ("W", 2),
    "gdp_saar": ("Q", 2),
    "gdp_yoy": ("Q", 2),
    "payrolls_chg": ("M", 0),
    "payrolls_3mma": ("M", 1),
    "umcsent": ("M", 1),
}


def to_columns(s: pd.Series, decimals: int) -> dict[str, list[Any]]:
    s = s.dropna()
    return {
        "t": [d.strftime("%Y-%m-%d") for d in s.index],
        "v": [tf.clean_number(x, decimals) for x in s.to_numpy()],
    }


# --------------------------------------------------------------------------- KPIs


def _spark(s: pd.Series, freq: str) -> list[float | None]:
    s = s.dropna()
    if freq == "D":
        s = s.loc[s.index >= s.index[-1] - pd.Timedelta(days=365)]
        s = s.groupby(s.index.to_period("W-FRI")).tail(1)
    elif freq == "W":
        s = s.iloc[-52:]
    elif freq == "Q":
        s = s.iloc[-16:]
    else:
        s = s.iloc[-36:]
    return [tf.clean_number(x, 3) for x in s.to_numpy()]


def kpi(
    key: str,
    label: str,
    s: pd.Series,
    *,
    unit: str,
    decimals: int,
    good: str | None,
    fred_id: str,
    chart: str,
    compare: str = "year",
    note: Callable[[], str] | None = None,
    signed: bool = False,
) -> dict[str, Any]:
    """One KPI card: latest value, change vs a comparison point, sparkline."""
    s = s.dropna()
    freq = SERIES_FMT.get(key, ("M", decimals))[0]
    last_date, last = s.index[-1], float(s.iloc[-1])
    if compare == "prior":
        prev_date, prev = s.index[-2], float(s.iloc[-2])
    else:
        found = tf.value_as_of(s, YEAR)
        prev_date, prev = found if found else (None, float("nan"))
    delta = last - prev
    return {
        "key": key,
        "label": label,
        "fred_id": fred_id,
        "chart": chart,
        "freq": freq,
        "unit": unit,
        "decimals": decimals,
        "signed": signed,
        "good": good,
        "date": last_date.strftime("%Y-%m-%d"),
        "value": tf.clean_number(last, decimals),
        "compare": {
            "label": "vs prior period" if compare == "prior" else "vs 1 yr ago",
            "date": prev_date.strftime("%Y-%m-%d") if prev_date is not None else None,
            "value": tf.clean_number(prev, decimals),
            "delta": tf.clean_number(delta, decimals),
        },
        "note": note() if note else None,
        "spark": _spark(s, freq),
    }


def build_kpis(d: dict[str, pd.Series]) -> list[dict[str, Any]]:
    p3 = d["payrolls_3mma"].iloc[-1]
    return [
        kpi(
            "unrate",
            "Unemployment rate",
            d["unrate"],
            unit="%",
            decimals=1,
            good="down",
            fred_id="UNRATE",
            chart="labor",
        ),
        kpi(
            "cpi_yoy",
            "CPI inflation (YoY)",
            d["cpi_yoy"],
            unit="%",
            decimals=1,
            good="down",
            fred_id="CPIAUCSL",
            chart="inflation",
        ),
        kpi(
            "core_yoy",
            "Core CPI (YoY)",
            d["core_yoy"],
            unit="%",
            decimals=1,
            good="down",
            fred_id="CPILFESL",
            chart="inflation",
            note=lambda: f"3-mo annualized {d['core_3m_ann'].iloc[-1]:.1f}%",
        ),
        kpi(
            "payrolls_chg",
            "Payroll job gains",
            d["payrolls_chg"],
            unit="k",
            decimals=0,
            good="up",
            fred_id="PAYEMS",
            chart="jobs",
            signed=True,
            compare="prior",
            note=lambda: f"3-mo avg {p3:+,.0f}k",
        ),
        kpi(
            "gdp_saar",
            "Real GDP growth",
            d["gdp_saar"],
            unit="%",
            decimals=1,
            good="up",
            fred_id="GDPC1",
            chart="gdp",
            signed=True,
            compare="prior",
            note=lambda: f"{d['gdp_yoy'].iloc[-1]:.1f}% vs year earlier",
        ),
        kpi(
            "fedfunds",
            "Fed funds rate",
            d["fedfunds"],
            unit="%",
            decimals=2,
            good=None,
            fred_id="FEDFUNDS",
            chart="rates",
        ),
        kpi(
            "dgs10",
            "10-yr Treasury",
            d["dgs10"],
            unit="%",
            decimals=2,
            good=None,
            fred_id="DGS10",
            chart="rates",
        ),
        kpi(
            "spread_10y2y",
            "10y\u20132y spread",
            d["spread_10y2y"],
            unit="pp",
            decimals=2,
            good=None,
            fred_id="DGS10\u2212DGS2",
            chart="curve",
            signed=True,
        ),
        kpi(
            "mortgage30",
            "30-yr mortgage",
            d["mortgage30"],
            unit="%",
            decimals=2,
            good="down",
            fred_id="MORTGAGE30US",
            chart="rates",
        ),
        kpi(
            "umcsent",
            "Consumer sentiment",
            d["umcsent"],
            unit="",
            decimals=1,
            good="up",
            fred_id="UMCSENT",
            chart="sentiment",
        ),
    ]


# --------------------------------------------------------------------------- signals


def build_signals(d: dict[str, pd.Series]) -> dict[str, Any]:
    sahm = d["sahm"]
    spread = d["spread_10y2y"]
    episodes = tf.inversion_episodes(spread, min_days=30)
    last_ep = episodes[-1] if episodes else None
    as_of = spread.index[-1]
    core = d["core_yoy"]
    ff = d["fedfunds"]
    real_rate_date = min(core.index[-1], ff.index[-1])

    def ep_json(e: tf.Episode) -> dict[str, Any]:
        seg = spread.loc[e.start : e.end]
        return {
            "start": e.start.strftime("%Y-%m-%d"),
            "end": e.end.strftime("%Y-%m-%d"),
            "days": e.days,
            "ongoing": e.ongoing,
            "min": tf.clean_number(seg.min(), 2),
        }

    return {
        "sahm": {
            "value": tf.clean_number(sahm.iloc[-1], 2),
            "date": sahm.index[-1].strftime("%Y-%m-%d"),
            "threshold": tf.SAHM_THRESHOLD,
            "triggered": bool(sahm.iloc[-1] >= tf.SAHM_THRESHOLD),
            "max_12m": tf.clean_number(sahm.iloc[-12:].max(), 2),
        },
        "curve": {
            "spread": tf.clean_number(spread.iloc[-1], 2),
            "date": as_of.strftime("%Y-%m-%d"),
            "inverted": bool(spread.iloc[-1] < 0),
            "last_inversion": ep_json(last_ep) if last_ep else None,
            "days_since_inversion": (
                None if last_ep is None or last_ep.ongoing else int((as_of - last_ep.end).days)
            ),
            "episodes": [ep_json(e) for e in episodes],
        },
        "inflation": {
            "core_yoy": tf.clean_number(core.iloc[-1], 2),
            "target": INFLATION_TARGET,
            "gap": tf.clean_number(core.iloc[-1] - INFLATION_TARGET, 2),
            "date": core.index[-1].strftime("%Y-%m-%d"),
        },
        "real_rate": {
            "value": tf.clean_number(
                ff.loc[:real_rate_date].iloc[-1] - core.loc[:real_rate_date].iloc[-1], 2
            ),
            "date": real_rate_date.strftime("%Y-%m-%d"),
        },
    }


# --------------------------------------------------------------------------- payload


def data_gap_notes(raw: dict[str, pd.Series], since: str = "2015-01-01") -> list[str]:
    """Human-readable notes about recent missing releases, generated from the data."""
    notes = []
    for sid in ("UNRATE", "CPIAUCSL", "CPILFESL", "PAYEMS", "UMCSENT"):
        gaps = tf.missing_periods(raw[sid], since=since)
        if gaps:
            when = ", ".join(g.strftime("%b %Y") for g in gaps)
            notes.append(f"{SERIES[sid].name} ({sid}) has no observation for {when}.")
    if notes:
        notes.append(
            "Year-over-year and annualized changes whose base period is a single "
            "missing month use a log-linear interpolation of the neighbouring months; "
            "the missing month itself is left blank on the charts."
        )
    return notes


def build_payload(
    raw: dict[str, pd.Series],
    meta: dict[str, dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Pure: raw FRED series in, (summary, series) JSON-ready dicts out."""
    now = now or datetime.now(UTC)
    d = derive(raw)
    recessions = tf.recession_periods(raw["USREC"])
    meta = meta or {}
    summary = {
        "schema": 1,
        "notes": data_gap_notes(raw),
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": {
            "name": "FRED\u00ae, Federal Reserve Bank of St. Louis",
            "url": "https://fred.stlouisfed.org/",
            "notice": FRED_NOTICE,
        },
        "kpis": build_kpis(d),
        "signals": build_signals(d),
        "recessions": recessions,
        "fred": {
            sid: {
                "title": meta.get(sid, {}).get("title", s.name),
                "units": meta.get(sid, {}).get("units_short", s.units),
                "frequency": s.frequency,
                "last_updated": meta.get(sid, {}).get("last_updated"),
                "observation_end": (raw[sid].index[-1].strftime("%Y-%m-%d") if not raw[sid].empty else None),
            }
            for sid, s in SERIES.items()
        },
    }
    series = {
        "schema": 1,
        "generated_at": summary["generated_at"],
        "recessions": recessions,
        "series": {
            key: to_columns(tf.thin_daily(s) if SERIES_FMT[key][0] == "D" else s, SERIES_FMT[key][1])
            for key, s in d.items()
        },
    }
    return summary, series


def write_json(obj: Any, path: Path) -> int:
    text = json.dumps(obj, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text + "\n", encoding="utf-8")
    tmp.replace(path)  # atomic: the site never sees a half-written file
    return len(text)


def fetch_all(client: Any) -> tuple[dict[str, pd.Series], dict[str, dict[str, Any]]]:
    raw, meta = {}, {}
    for sid in SERIES:
        raw[sid] = client.observations(sid)
        meta[sid] = client.series_info(sid)
        log.info("%-13s %6d obs  last %s", sid, len(raw[sid]), raw[sid].index[-1].date())
    return raw, meta


def main(argv: list[str] | None = None) -> int:
    from .fred import FredClient, FredError

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=Path("site/data"))
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        raw, meta = fetch_all(FredClient())
    except FredError as exc:
        log.error("error: %s", exc)
        return 1
    summary, series = build_payload(raw, meta)
    args.out.mkdir(parents=True, exist_ok=True)
    n1 = write_json(summary, args.out / "summary.json")
    n2 = write_json(series, args.out / "series.json")
    log.info("wrote summary.json (%.1f KB) and series.json (%.1f KB)", n1 / 1024, n2 / 1024)
    return 0


if __name__ == "__main__":
    sys.exit(main())
