"""AlpacaDataProvider 테스트 (네트워크 없이 HTTP 응답만 가짜로).

여기서 지키려는 것 중 제일 중요한 것:
**Alpaca 의 start/end 는 배당락일(ex_date)이 아니라 처리일(process_date) 기준으로 거릅니다.**
그래서 조회 구간을 미래로 넉넉히 늘려 받지 않으면, 월배당 종목의 가장 최근 배당이
매번 누락되어 분배금이 낮게 나옵니다 (실제로 O 에서 발견된 버그).
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from data.providers import alpaca_provider as ap
from data.providers.base import DataUnavailable
from data.providers.fallback_provider import FallbackProvider


@pytest.fixture(autouse=True)
def _creds(monkeypatch):
    monkeypatch.setattr(ap, "credentials", lambda: ("key", "secret"))
    from data.providers import cache
    cache.invalidate()
    yield
    cache.invalidate()


class FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.text = str(payload)

    def json(self):
        return self._payload


def test_history_requests_split_adjustment_not_all(monkeypatch):
    """adjustment=all 을 쓰면 배당이 가격에도 반영돼 분배금이 이중 계산됩니다.
    반드시 split 이어야 합니다."""
    seen = {}

    def fake_get(url, headers=None, params=None, timeout=None):
        seen.update(params)
        return FakeResp({"bars": [{"t": "2026-01-05T05:00:00Z", "c": 100.0}]})

    monkeypatch.setattr(ap.requests, "get", fake_get)
    df = ap.AlpacaDataProvider().get_price_history("SCHD", date(2026, 1, 1), date(2026, 1, 31))

    assert seen["adjustment"] == "split"
    assert df["close"].iloc[0] == 100.0
    assert df.attrs["source"] == "alpaca"


def test_dividend_query_window_extends_into_the_future(monkeypatch):
    """가장 최근 배당(지급일이 아직 미래)이 빠지지 않도록 조회 끝날짜를 늘려야 한다."""
    seen = {}

    def fake_get(url, headers=None, params=None, timeout=None):
        seen.update(params)
        return FakeResp({"corporate_actions": {"cash_dividends": []}})

    monkeypatch.setattr(ap.requests, "get", fake_get)
    today = date.today()
    ap.AlpacaDataProvider().get_distributions("O", today - timedelta(days=365), today)

    assert date.fromisoformat(seen["end"]) > today, \
        "조회 끝날짜가 오늘이면 지급일이 미래인 최근 배당이 누락됩니다."


def test_dividends_are_indexed_by_ex_date_and_sliced_locally(monkeypatch):
    """Alpaca 가 처리일 기준으로 넓게 돌려줘도, 우리는 ex_date 기준으로 잘라야 한다."""
    payload = {"corporate_actions": {"cash_dividends": [
        {"ex_date": "2026-07-31", "rate": 0.271, "process_date": "2026-08-14"},
        {"ex_date": "2026-08-31", "rate": 0.271, "process_date": "2026-09-15"},
        {"ex_date": "2026-09-30", "rate": 0.2715, "process_date": "2026-10-15"},  # 미래
    ]}}
    monkeypatch.setattr(ap.requests, "get",
                        lambda *a, **k: FakeResp(payload))

    s = ap.AlpacaDataProvider().get_distributions("O", date(2026, 1, 1), date(2026, 9, 12))

    assert list(s.index.strftime("%Y-%m-%d")) == ["2026-07-31", "2026-08-31"]
    assert s.sum() == pytest.approx(0.542)     # 아직 배당락 전인 9/30 은 빠져야 함


def test_splits_ratio_is_new_over_old(monkeypatch):
    """10:1 분할 -> 10.0 (yfinance 의 splits 와 같은 표현)."""
    payload = {"corporate_actions": {"forward_splits": [
        {"ex_date": "2024-06-10", "old_rate": 1, "new_rate": 10},
    ]}}
    monkeypatch.setattr(ap.requests, "get", lambda *a, **k: FakeResp(payload))

    s = ap.AlpacaDataProvider().get_splits("NVDA", date(2024, 1, 1), date(2024, 12, 31))
    assert list(s.values) == [10.0]
    assert str(s.index[0].date()) == "2024-06-10"


def test_korean_ticker_is_rejected_clearly(monkeypatch):
    monkeypatch.setattr(ap.requests, "get",
                        lambda *a, **k: FakeResp({"message": "invalid symbol"}, status=400))
    with pytest.raises(DataUnavailable):
        ap.AlpacaDataProvider().get_latest_price("329200")


def test_rate_limit_message_is_understandable(monkeypatch):
    monkeypatch.setattr(ap.requests, "get", lambda *a, **k: FakeResp({}, status=429))
    with pytest.raises(DataUnavailable, match="한도"):
        ap.AlpacaDataProvider().get_latest_price("SCHD")


def test_no_keys_means_not_configured(monkeypatch):
    monkeypatch.setattr(ap, "credentials", lambda: None)
    assert ap.is_configured() is False


# ---- 폴백 -----------------------------------------------------------------
class _Boom:
    name = "boom"

    def get_latest_price(self, t):
        raise DataUnavailable("일부러 실패")

    def get_price_history(self, t, s, e):
        raise DataUnavailable("일부러 실패")

    def get_distributions(self, t, s, e):
        raise DataUnavailable("일부러 실패")

    def get_splits(self, t, s, e):
        raise DataUnavailable("일부러 실패")

    def get_info(self, t):
        return {}


class _Ok:
    name = "ok"

    def get_latest_price(self, t):
        from data.providers.base import PriceQuote
        return PriceQuote(ticker=t, price=1.0, currency="USD", as_of=date.today(), source=self.name)

    def get_price_history(self, t, s, e):
        return pd.DataFrame({"close": [1.0]}, index=pd.DatetimeIndex([pd.Timestamp("2026-01-02")]))

    def get_distributions(self, t, s, e):
        return pd.Series(dtype="float64")

    def get_splits(self, t, s, e):
        return pd.Series(dtype="float64")

    def get_info(self, t):
        return {}


def test_fallback_uses_second_source_when_first_fails():
    p = FallbackProvider(_Boom(), _Ok())
    q = p.get_latest_price("SCHD")
    assert q.source == "ok"          # 어디서 왔는지 출처가 그대로 남는다
    assert p.name == "boom+ok"


def test_fallback_prefers_primary_when_it_works():
    p = FallbackProvider(_Ok(), _Boom())
    assert p.get_latest_price("SCHD").source == "ok"


# ---- 미국 종목 소스 배분 ---------------------------------------------------
def test_us_composite_uses_alpaca_for_live_and_yahoo_for_history():
    """Alpaca 무료 티어는 과거가 2020년 중반까지만이라, 오래된 백테스트가 막힙니다.
    그래서 잦은 호출(최신가·분배금)만 Alpaca 로 보내고, 히스토리는 yfinance 를 먼저 씁니다."""
    from data.providers.us_composite import USCompositeProvider

    class _Alpaca(_Ok):
        name = "alpaca"

    class _Yahoo(_Ok):
        name = "yfinance"

    p = USCompositeProvider(_Alpaca(), _Yahoo())
    assert p.get_latest_price("SCHD").source == "alpaca"
    assert p.get_price_history("SCHD", date(2015, 1, 1), date(2026, 1, 1)) \
        .attrs.get("source", "yfinance") == "yfinance"


def test_us_composite_still_works_when_alpaca_is_down():
    from data.providers.us_composite import USCompositeProvider

    class _Yahoo(_Ok):
        name = "yfinance"

    p = USCompositeProvider(_Boom(), _Yahoo())
    assert p.get_latest_price("SCHD").source == "yfinance"
    assert len(p.get_distributions("SCHD", date(2026, 1, 1), date(2026, 2, 1))) == 0
