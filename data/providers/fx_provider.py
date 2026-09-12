"""
data/providers/fx_provider.py  --  USD/KRW 환율 데이터 (인수인계서 50~52)
=====================================================================

가장 중요한 원칙 (인수인계서 51):
    과거 백테스트에서는 "과거 주가 + 과거 환율" 을 사용한다.
    "과거 주가 + 현재 환율" 을 절대 사용하지 않는다.

- get_rate_on(d)     : 특정 날짜(또는 그 이전 가장 가까운 거래일)의 환율  -> 백테스트용
- get_latest_rate()  : 가장 최근 환율                                      -> 현재 포트폴리오용

1차 소스: yfinance "USDKRW=X"
보조 소스: FinanceDataReader "USD/KRW"
둘 다 실패하면 DataUnavailable (추정 금지 -- 인수인계서 52)
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

import config
from data.providers import cache
from data.providers.base import DataUnavailable, FxQuote
from data.providers import us_provider

try:
    import FinanceDataReader as fdr
except Exception:  # pragma: no cover
    fdr = None


def _fdr_usdkrw_history(start: date, end: date) -> pd.Series:
    if fdr is None:
        raise DataUnavailable("FinanceDataReader 를 사용할 수 없습니다.")
    raw = fdr.DataReader("USD/KRW", start.isoformat(), end.isoformat())
    if raw is None or raw.empty or "Close" not in raw.columns:
        raise DataUnavailable(f"{start}~{end} 구간의 USD/KRW 환율(FDR)을 가져오지 못했습니다.")
    raw = raw.dropna(subset=["Close"])
    raw = raw[raw["Close"] > 0]
    if raw.empty:
        raise DataUnavailable(f"{start}~{end} 구간에 유효한 USD/KRW 환율(FDR)이 없습니다.")
    idx = pd.DatetimeIndex(pd.to_datetime([d.date() if hasattr(d, "date") else d
                                           for d in raw.index]), name="date")
    return pd.Series(raw["Close"].to_numpy(), index=idx, name="usdkrw")


def get_history(start: date, end: date) -> pd.Series:
    """USD/KRW 일별 환율 시계열. yfinance -> FDR 순으로 시도."""
    key = f"fx:usdkrw:merged:{start}:{end}"

    def _load() -> pd.Series:
        errors = []
        for loader in (us_provider.fetch_usdkrw_history, _fdr_usdkrw_history):
            try:
                s = loader(start, end)
                if s is not None and len(s) > 0:
                    return s.sort_index()
            except Exception as e:  # noqa: BLE001 - 다음 소스로 폴백
                errors.append(str(e))
        raise DataUnavailable(
            "USD/KRW 환율 데이터를 어떤 소스에서도 가져오지 못했습니다. " + " / ".join(errors)
        )

    return cache.get_or_set(key, config.CACHE_TTL_FX_SECONDS, _load)


def get_latest_rate() -> FxQuote:
    """가장 최근 USD/KRW 환율 (현재 포트폴리오 계산용)."""
    key = "fx:usdkrw:latest"

    def _load() -> FxQuote:
        today = date.today()
        s = get_history(today - timedelta(days=14), today)
        last_dt = s.index.max()
        return FxQuote(pair="USD/KRW", rate=float(s.loc[last_dt]),
                       as_of=last_dt.date(), source="yfinance/FDR")

    return cache.get_or_set(key, config.CACHE_TTL_FX_SECONDS, _load)


def get_rate_on(d: date) -> FxQuote:
    """날짜 d 의 환율. d 가 거래일이 아니면 d "이전" 가장 가까운 거래일 환율을 사용.

    (백테스트에서 특정 매수 기준일의 환율을 구할 때 사용 -- 인수인계서 50, 72)
    """
    key = f"fx:usdkrw:on:{d}"

    def _load() -> FxQuote:
        s = get_history(d - timedelta(days=14), d + timedelta(days=1))
        on_or_before = s.loc[s.index <= pd.Timestamp(d)]
        if on_or_before.empty:
            raise DataUnavailable(f"{d} 또는 그 이전의 USD/KRW 환율 데이터를 가져올 수 없습니다.")
        last_dt = on_or_before.index.max()
        return FxQuote(pair="USD/KRW", rate=float(on_or_before.loc[last_dt]),
                       as_of=last_dt.date(), source="yfinance/FDR")

    return cache.get_or_set(key, config.CACHE_TTL_FX_SECONDS, _load)
