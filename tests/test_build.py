import json
from datetime import UTC, datetime

import pytest

from pipeline.build import build_payload, write_json


@pytest.fixture
def payload(synthetic_raw):
    return build_payload(synthetic_raw, now=datetime(2024, 1, 2, tzinfo=UTC))


def test_summary_shape(payload):
    summary, _ = payload
    assert summary["generated_at"] == "2024-01-02T00:00:00Z"
    assert "not endorsed" in summary["source"]["notice"]
    keys = [k["key"] for k in summary["kpis"]]
    assert {"unrate", "cpi_yoy", "spread_10y2y", "gdp_saar", "payrolls_chg"} <= set(keys)
    for k in summary["kpis"]:
        assert k["value"] is not None and k["spark"], k["key"]


def test_kpi_values_follow_inputs(payload):
    summary, _ = payload
    by = {k["key"]: k for k in summary["kpis"]}
    assert by["unrate"]["value"] == 5.0
    assert by["cpi_yoy"]["value"] == pytest.approx((1.003**12 - 1) * 100, abs=0.05)
    assert by["payrolls_chg"]["value"] == 150
    assert by["gdp_saar"]["value"] == pytest.approx((1.006**4 - 1) * 100, abs=0.05)


def test_signals(payload):
    summary, _ = payload
    sig = summary["signals"]
    assert sig["sahm"]["triggered"] is True  # unemployment rose 1.4 pp in synthetic data
    assert sig["inflation"]["gap"] == pytest.approx(sig["inflation"]["core_yoy"] - 2.0, abs=0.01)
    assert [list(r) for r in summary["recessions"]] == [["2021-10", "2022-03"]]


def test_series_are_columnar_and_aligned(payload):
    _, series = payload
    for key, col in series["series"].items():
        assert len(col["t"]) == len(col["v"]) > 0, key
        assert col["t"] == sorted(col["t"]), key


def test_json_is_strict_and_atomic(payload, tmp_path):
    summary, _ = payload
    out = tmp_path / "summary.json"
    write_json(summary, out)
    assert json.loads(out.read_text())["schema"] == 1
    assert not list(tmp_path.glob("*.tmp"))
