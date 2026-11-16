import numpy as np
import pandas as pd
import pytest


def monthly(values, start="2020-01-01"):
    return pd.Series(
        np.asarray(values, dtype=float),
        index=pd.date_range(start, periods=len(values), freq="MS"),
    )


@pytest.fixture
def synthetic_raw():
    """Small but complete raw-series bundle shaped like real FRED output."""
    n = 60
    months = pd.date_range("2018-01-01", periods=n, freq="MS")
    days = pd.bdate_range("2018-01-01", months[-1] + pd.offsets.MonthEnd(0))
    weeks = pd.date_range("2018-01-04", months[-1], freq="W-THU")
    quarters = pd.date_range("2018-01-01", months[-1], freq="QS-JAN")
    rng = np.random.default_rng(0)
    unrate = np.r_[np.full(40, 3.6), np.linspace(3.6, 5.0, 20)]
    usrec = np.r_[np.zeros(45), np.ones(6), np.zeros(9)]
    return {
        "UNRATE": pd.Series(unrate, months),
        "CPIAUCSL": pd.Series(250 * 1.003 ** np.arange(n), months),
        "CPILFESL": pd.Series(260 * 1.0025 ** np.arange(n), months),
        "FEDFUNDS": pd.Series(np.linspace(1.5, 4.0, n), months),
        "DGS10": pd.Series(3 + rng.normal(0, 0.05, len(days)).cumsum() * 0.1, days),
        "DGS2": pd.Series(2.5 + rng.normal(0, 0.05, len(days)).cumsum() * 0.1, days),
        "GDPC1": pd.Series(20000 * 1.006 ** np.arange(len(quarters)), quarters),
        "PAYEMS": pd.Series(150000 + 150 * np.arange(n), months),
        "UMCSENT": pd.Series(np.linspace(95, 60, n), months),
        "MORTGAGE30US": pd.Series(np.linspace(4, 7, len(weeks)), weeks),
        "USREC": pd.Series(usrec, months),
    }
