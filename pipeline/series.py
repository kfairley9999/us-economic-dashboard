"""Catalogue of FRED series pulled by the pipeline.

Each entry records how the raw series should be treated downstream: its native
frequency, display units, and how its history is thinned before being shipped
to the browser.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Series:
    id: str
    name: str
    units: str
    frequency: str  # "D", "W", "M", or "Q": the native FRED frequency
    decimals: int = 2


SERIES: dict[str, Series] = {
    s.id: s
    for s in (
        Series("UNRATE", "Unemployment rate", "%", "M", 1),
        Series("CPIAUCSL", "Consumer Price Index (all items)", "index 1982-84=100", "M", 3),
        Series("CPILFESL", "Core CPI (ex food & energy)", "index 1982-84=100", "M", 3),
        Series("FEDFUNDS", "Effective federal funds rate", "%", "M", 2),
        Series("DGS10", "10-year Treasury yield", "%", "D", 2),
        Series("DGS2", "2-year Treasury yield", "%", "D", 2),
        Series("GDPC1", "Real GDP", "bn chained 2017 $", "Q", 1),
        Series("PAYEMS", "Nonfarm payrolls", "thousands", "M", 0),
        Series("UMCSENT", "Consumer sentiment (U. Michigan)", "index 1966Q1=100", "M", 1),
        Series("MORTGAGE30US", "30-year fixed mortgage rate", "%", "W", 2),
        Series("USREC", "NBER recession indicator", "0/1", "M", 0),
    )
}
