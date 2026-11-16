import pandas as pd
import pytest
import requests

from pipeline.fred import FredClient, FredError, parse_observations

SECRET = "abcd1234secretkey"


class FakeResponse:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload or {}
        self.url = f"https://api.stlouisfed.org/fred/x?api_key={SECRET}"

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.headers = {}
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append(params)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def test_parse_observations_handles_missing_dot():
    obs = [{"date": "2024-01-01", "value": "3.7"}, {"date": "2024-02-01", "value": "."}]
    s = parse_observations(obs, "UNRATE")
    assert list(s.index) == [pd.Timestamp("2024-01-01")] and s.iloc[0] == 3.7


def test_retries_then_succeeds():
    ok = FakeResponse(200, {"observations": [{"date": "2024-01-01", "value": "1"}]})
    sess = FakeSession([FakeResponse(503), ok])
    s = FredClient(SECRET, session=sess, backoff=0).observations("X")
    assert len(sess.calls) == 2 and s.iloc[0] == 1.0


@pytest.mark.parametrize(
    "response",
    [FakeResponse(400), requests.ConnectionError(f"failed for url ...api_key={SECRET}")],
)
def test_errors_never_leak_the_key(response):
    sess = FakeSession([response] * 5)
    with pytest.raises(FredError) as exc:
        FredClient(SECRET, session=sess, retries=1, backoff=0).observations("UNRATE")
    assert SECRET not in str(exc.value) and "UNRATE" in str(exc.value)
    assert exc.value.__cause__ is None
    assert exc.value.__context__ is None or exc.value.__suppress_context__


def test_missing_key(monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    with pytest.raises(FredError, match="not set"):
        FredClient()
