import math

import numpy as np
import pandas as pd
import pytest

from pipeline import transforms as tf
from tests.conftest import monthly


def test_yoy_pct_matches_hand_calculation():
    s = monthly([100] * 12 + [103])
    assert tf.yoy_pct(s).iloc[-1] == pytest.approx(3.0)
    assert tf.yoy_pct(s).iloc[:12].isna().all()


def test_yoy_pct_is_calendar_aligned_not_positional():
    # Drop one month: a positional shift(12) would compare against the wrong month.
    s = monthly(np.arange(100, 125, dtype=float))
    gappy = s.drop(s.index[5])
    expected = (s / s.shift(12) - 1) * 100
    got = tf.yoy_pct(gappy)
    common = got.dropna().index.drop(pd.Timestamp("2021-06-01"))  # base month interpolated
    pd.testing.assert_series_equal(got.loc[common], expected.loc[common], check_names=False)
    positional = ((gappy / gappy.shift(12) - 1) * 100).loc[common].dropna()
    assert not np.allclose(positional, expected.loc[positional.index])


def test_single_missing_base_month_is_interpolated_geometrically():
    s = monthly([100.0, 0, 121.0] + [130.0] * 11)
    s = s.drop(s.index[1])  # month 2 missing; geometric midpoint = 110
    filled = tf.fill_single_gaps(s)
    assert filled.iloc[1] == pytest.approx(110.0)
    yoy = tf.yoy_pct(s)
    # 13th month (index 13 -> Feb next year) compares against interpolated 110
    assert yoy.loc["2021-02-01"] == pytest.approx((130 / 110 - 1) * 100)
    assert "2020-02-01" not in yoy.index  # the missing month itself never appears


def test_longer_gaps_are_not_filled():
    s = monthly(np.arange(1, 13, dtype=float))
    s = s.drop(s.index[[4, 5]])
    assert tf.fill_single_gaps(s).isna().sum() == 2
    assert [d.month for d in tf.missing_periods(s)] == [5, 6]


def test_annualized_quarterly_growth():
    q = pd.Series([100.0, 101.0], index=pd.to_datetime(["2024-01-01", "2024-04-01"]))
    assert tf.annualized_pct(q, 3).iloc[-1] == pytest.approx((1.01**4 - 1) * 100)


def test_three_month_annualized_monthly():
    s = monthly([100, 100.5, 101, 101.5])
    assert tf.annualized_pct(s, 3).iloc[-1] == pytest.approx((1.015**4 - 1) * 100)


def test_monthly_change():
    s = monthly([150_000, 150_200, 150_150])
    assert tf.monthly_change(s).tolist()[1:] == [200, -50]


def test_sahm_rule_flat_unemployment_is_zero():
    s = monthly([4.0] * 24)
    assert tf.sahm_rule(s).dropna().abs().max() == 0


def test_sahm_rule_triggers_on_half_point_rise():
    # 15 flat months at 3.5%, then the rate climbs 0.25 pp a month.
    s = monthly([3.5] * 15 + [3.75, 4.0, 4.25, 4.5])
    sahm = tf.sahm_rule(s)
    # 3-mo average of last three = 4.25; prior 12-mo minimum of the average = 3.5
    assert sahm.iloc[-1] == pytest.approx(0.75)
    assert (sahm >= tf.SAHM_THRESHOLD).iloc[-1]
    assert not (sahm.iloc[:15] >= tf.SAHM_THRESHOLD).any()


def test_sahm_rule_tolerates_one_missing_month():
    s = monthly([4.0] * 20).drop(pd.Timestamp("2021-01-01"))
    sahm = tf.sahm_rule(s)
    assert sahm.index.equals(s.index)
    assert sahm.iloc[-1] == pytest.approx(0.0)


def test_spread_aligns_on_common_dates():
    idx = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    long = pd.Series([4.0, 4.1, np.nan], idx)
    short = pd.Series([4.5, np.nan, 4.0], idx)
    out = tf.spread(long, short)
    assert list(out.index) == [idx[0]]
    assert out.iloc[0] == pytest.approx(-0.5)


def test_inversion_episodes_and_min_days_filter():
    idx = pd.date_range("2024-01-01", periods=10, freq="D")
    s = pd.Series([0.2, -0.1, -0.2, 0.1, -0.3, -0.3, -0.3, -0.3, 0.2, -0.1], idx)
    eps = tf.inversion_episodes(s)
    assert [(e.start.day, e.end.day) for e in eps] == [(2, 3), (5, 8), (10, 10)]
    assert eps[-1].ongoing and not eps[0].ongoing
    assert [e.days for e in tf.inversion_episodes(s, min_days=3)] == [4]


def test_recession_periods():
    s = monthly([0, 1, 1, 0, 0, 1], start="2020-01-01")
    assert tf.recession_periods(s) == [("2020-02", "2020-03"), ("2020-06", "2020-06")]


def test_value_as_of_uses_latest_on_or_before_target():
    s = monthly(range(14))
    date, val = tf.value_as_of(s, pd.DateOffset(years=1))
    assert date == pd.Timestamp("2020-02-01") and val == 1
    assert tf.value_as_of(monthly([1.0]), pd.DateOffset(years=1)) is None


def test_thin_daily_keeps_recent_daily_and_weekly_history():
    idx = pd.bdate_range("2015-01-01", "2024-12-31")
    s = pd.Series(np.arange(len(idx), dtype=float), idx)
    out = tf.thin_daily(s, full_res_days=365)
    recent = out.loc[out.index >= idx[-1] - pd.Timedelta(days=365)]
    old = out.loc[out.index < idx[-1] - pd.Timedelta(days=365)]
    assert len(recent) == len(s.loc[recent.index[0] :])
    assert pd.Series(old.index).diff().dropna().dt.days.min() >= 3
    assert out.index.is_monotonic_increasing and len(out) < len(s) / 3


@pytest.mark.parametrize(
    "x,expected", [(1.23456, 1.23), (float("nan"), None), (float("inf"), None), (-0.001, 0.0), (None, None)]
)
def test_clean_number(x, expected):
    got = tf.clean_number(x, 2)
    assert got == expected
    if got == 0.0:
        assert math.copysign(1, got) == 1
