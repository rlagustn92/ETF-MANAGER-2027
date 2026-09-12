"""테스트 공용 픽스처: 네트워크 없이 동작하는 가짜(fake) 데이터 provider.

인수인계서 115 의 체크리스트(정수주, 환율, 분배금, 휴장일/상장전 백테스트, 분할, API 실패,
데이터 없음 등)를 외부 API 없이 재현하기 위한 도구입니다.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from data.providers.base import (
    DataUnavailable,
    HISTORY_CLOSE_COL,
    MarketDataProvider,
    PriceQuote,
)


class FakeProvider(MarketDataProvider):
    """스펙(dict)으로 동작을 지정하는 가짜 provider.

    spec[ticker] = {
        "currency": "USD"|"KRW",
        "latest": float | "error",
        "history": pd.Series (index=Timestamp, value=close) | "error",
        "distributions": pd.Series | "error" | None,
        "splits": pd.Series | None,
    }
    """

    def __init__(self, name: str, spec: dict):
        self.name = name
        self._spec = spec

    def _entry(self, ticker: str) -> dict:
        if ticker not in self._spec:
            raise DataUnavailable(f"[{ticker}] 테스트 스펙에 없는 종목입니다.")
        return self._spec[ticker]

    def get_latest_price(self, ticker: str) -> PriceQuote:
        e = self._entry(ticker)
        v = e.get("latest", "error")
        if v == "error" or v is None:
            raise DataUnavailable(f"[{ticker}] 가격 데이터 없음(테스트).")
        return PriceQuote(ticker=ticker, price=float(v), currency=e.get("currency", "USD"),
                          as_of=date(2026, 9, 10), source=self.name)

    def get_price_history(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        e = self._entry(ticker)
        h = e.get("history", "error")
        if isinstance(h, str) and h == "error":
            raise DataUnavailable(f"[{ticker}] 히스토리 없음(테스트).")
        s = h.copy()
        s.index = pd.DatetimeIndex(s.index, name="date")
        mask = (s.index >= pd.Timestamp(start)) & (s.index <= pd.Timestamp(end))
        sub = s.loc[mask]
        if sub.empty:
            raise DataUnavailable(f"[{ticker}] {start}~{end} 구간 데이터 없음(테스트).")
        df = pd.DataFrame({HISTORY_CLOSE_COL: sub.to_numpy()}, index=sub.index)
        df.attrs["currency"] = e.get("currency", "USD")
        df.attrs["source"] = self.name
        return df

    def get_distributions(self, ticker: str, start: date, end: date) -> pd.Series:
        e = self._entry(ticker)
        d = e.get("distributions", None)
        if isinstance(d, str) and d == "error":
            raise DataUnavailable(f"[{ticker}] 분배금 데이터 없음(테스트).")
        if d is None:
            return pd.Series(dtype="float64", index=pd.DatetimeIndex([], name="date"))
        s = d.copy()
        s.index = pd.DatetimeIndex(s.index, name="date")
        mask = (s.index >= pd.Timestamp(start)) & (s.index <= pd.Timestamp(end))
        return s.loc[mask]

    def get_splits(self, ticker: str, start: date, end: date) -> pd.Series:
        e = self._entry(ticker)
        sp = e.get("splits", None)
        if sp is None:
            return pd.Series(dtype="float64", index=pd.DatetimeIndex([], name="date"))
        s = sp.copy()
        s.index = pd.DatetimeIndex(s.index, name="date")
        mask = (s.index >= pd.Timestamp(start)) & (s.index <= pd.Timestamp(end))
        return s.loc[mask]


@pytest.fixture
def market(monkeypatch):
    """가짜 시장 데이터를 설치하는 픽스처.

    사용:
        market.set_us({...}); market.set_kr({...}); market.set_fx(rate=1400, history=series)
    """
    state: dict = {"US": {}, "KR": {}, "fx_rate": 1400.0, "fx_hist": None, "fx_ok": True}

    us_provider_obj = FakeProvider("FakeUS", state["US"])
    kr_provider_obj = FakeProvider("FakeKR", state["KR"])

    def fake_get_provider(mk: str):
        mk = (mk or "").upper()
        if mk == "US":
            return us_provider_obj
        if mk == "KR":
            return kr_provider_obj
        raise ValueError(f"unknown market {mk}")

    # 각 소비 모듈에 import 된 이름을 교체
    import services.portfolio_service as ps
    import services.distribution_service as ds
    import services.backtest_service as bs
    import services.fx_service as fxs

    monkeypatch.setattr(ps, "get_provider", fake_get_provider)
    monkeypatch.setattr(ds, "get_provider", fake_get_provider)
    monkeypatch.setattr(bs, "get_provider", fake_get_provider)

    from services.fx_service import FxResult

    def fake_current():
        if not state["fx_ok"]:
            return FxResult(rate=None, as_of=None, source="", ok=False,
                            message="USD/KRW 환율 데이터 없음(테스트).")
        return FxResult(rate=state["fx_rate"], as_of=date(2026, 9, 10), source="fake", ok=True)

    def fake_on(d):
        h = state["fx_hist"]
        if h is None:
            return fake_current()
        sub = h.loc[h.index <= pd.Timestamp(d)]
        if sub.empty:
            return FxResult(rate=None, as_of=None, source="", ok=False,
                            message="과거 환율 없음(테스트).")
        return FxResult(rate=float(sub.iloc[-1]), as_of=sub.index[-1].date(), source="fake", ok=True)

    monkeypatch.setattr(fxs, "current_usdkrw", fake_current)
    monkeypatch.setattr(fxs, "usdkrw_on", fake_on)
    monkeypatch.setattr(ps.fx_service, "current_usdkrw", fake_current, raising=True)

    # backtest_service 는 fx_provider.get_history 를 직접 부름
    import data.providers.fx_provider as fxp

    def fake_fx_history(start, end):
        h = state["fx_hist"]
        if h is None:
            idx = pd.date_range("2000-01-01", "2035-01-01", freq="D")
            return pd.Series(state["fx_rate"], index=idx, name="usdkrw")
        return h

    monkeypatch.setattr(bs.fx_provider, "get_history", fake_fx_history, raising=True)

    class _Ctl:
        def set_us(self, spec): state["US"].clear(); state["US"].update(spec)
        def set_kr(self, spec): state["KR"].clear(); state["KR"].update(spec)
        def set_fx(self, rate=None, history=None, ok=True):
            if rate is not None: state["fx_rate"] = float(rate)
            state["fx_hist"] = history
            state["fx_ok"] = ok

    return _Ctl()


def series(pairs: list[tuple[str, float]]) -> pd.Series:
    idx = pd.DatetimeIndex([pd.Timestamp(d) for d, _ in pairs], name="date")
    return pd.Series([v for _, v in pairs], index=idx)


def daily_series(start: str, end: str, value) -> pd.Series:
    idx = pd.bdate_range(start, end)
    if callable(value):
        vals = [value(i, ts) for i, ts in enumerate(idx)]
    else:
        vals = [value] * len(idx)
    return pd.Series(vals, index=pd.DatetimeIndex(idx, name="date"))
