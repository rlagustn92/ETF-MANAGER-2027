"""
data/providers/us_provider.py  --  미국 주식/ETF 데이터 (yfinance)
=================================================================

설치 확인 (2026-09, 실행 검증 완료):
    yfinance 1.6.0
    Ticker.history(start, end, auto_adjust=False) ->
        columns: Open, High, Low, Close, Adj Close, Volume, Dividends, Stock Splits, Capital Gains
        index  : tz-aware DatetimeIndex (America/New_York), 마지막 행 Close 가 NaN 일 수 있음(장중)
    Ticker.dividends -> pandas.Series (tz-aware index, 주당 현금 분배금)
    Ticker.splits    -> pandas.Series (tz-aware index, 분할 비율)
    Ticker.fast_info -> dict-like, keys: lastPrice, currency, yearHigh, yearLow, ...

가격/조정종가/분배금/분할을 분리해서 다룹니다. (인수인계서 62, 112)
- close     : 실제 종가 (auto_adjust=False 의 "Close")  -> 매수/평가 가격
- adj_close : 조정종가 (참고용)
- dividends : 현금흐름
- splits    : 정합성 검증용
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

import config
from data.providers import cache
from data.providers.base import (
    DataUnavailable,
    FxQuote,
    HISTORY_ADJCLOSE_COL,
    HISTORY_CLOSE_COL,
    MarketDataProvider,
    PriceQuote,
)

try:
    import yfinance as yf
except Exception as _e:  # pragma: no cover
    yf = None
    _IMPORT_ERROR = _e
else:
    _IMPORT_ERROR = None


def _require_yf() -> None:
    if yf is None:
        raise DataUnavailable(
            f"yfinance 를 불러올 수 없습니다: {_IMPORT_ERROR}. 'pip install yfinance' 를 확인하세요."
        )


def _to_daily_index(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """tz 정보와 시간(HH:MM)을 제거하고 날짜만 남긴 DatetimeIndex."""
    return pd.DatetimeIndex(pd.to_datetime([d.date() if hasattr(d, "date") else d for d in idx]),
                            name="date")


class USDataProvider(MarketDataProvider):
    name = "yfinance"

    # ---------------------------------------------------------------
    def get_price_history(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        _require_yf()
        key = f"us:hist:{ticker}:{start}:{end}"

        def _load() -> pd.DataFrame:
            t = yf.Ticker(ticker)
            # yfinance 의 end 는 배타적(exclusive) 이므로 하루 더함
            raw = t.history(
                start=start.isoformat(),
                end=(end + timedelta(days=1)).isoformat(),
                auto_adjust=config.YFINANCE_AUTO_ADJUST,   # False: Close/Adj Close 분리
                actions=True,
            )
            if raw is None or raw.empty:
                raise DataUnavailable(
                    f"[{ticker}] {start}~{end} 구간의 미국 가격 데이터를 가져오지 못했습니다."
                )
            raw = raw.dropna(subset=["Close"])
            if raw.empty:
                raise DataUnavailable(
                    f"[{ticker}] {start}~{end} 구간에 유효한 종가가 없습니다."
                )
            df = pd.DataFrame(index=_to_daily_index(raw.index))
            df[HISTORY_CLOSE_COL] = raw["Close"].to_numpy()
            if "Adj Close" in raw.columns:
                df[HISTORY_ADJCLOSE_COL] = raw["Adj Close"].to_numpy()
            df.attrs["currency"] = "USD"
            df.attrs["source"] = self.name
            return df

        return cache.get_or_set(key, config.CACHE_TTL_PRICE_SECONDS, _load)

    # ---------------------------------------------------------------
    def get_latest_price(self, ticker: str) -> PriceQuote:
        _require_yf()
        key = f"us:last:{ticker}"

        def _load() -> PriceQuote:
            today = date.today()
            df = self.get_price_history(ticker, today - timedelta(days=10), today)
            last_dt = df.index.max()
            price = float(df.loc[last_dt, HISTORY_CLOSE_COL])
            return PriceQuote(
                ticker=ticker,
                price=price,
                currency="USD",
                as_of=last_dt.date(),
                source=self.name,
            )

        return cache.get_or_set(key, config.CACHE_TTL_LATEST_PRICE_SECONDS, _load)

    # ---------------------------------------------------------------
    def get_distributions(self, ticker: str, start: date, end: date) -> pd.Series:
        _require_yf()
        key = f"us:div:{ticker}"

        def _load_all() -> pd.Series:
            s = yf.Ticker(ticker).dividends
            if s is None:
                raise DataUnavailable(f"[{ticker}] 분배금 데이터를 가져오지 못했습니다.")
            s = s.copy()
            if len(s) == 0:
                # 진짜로 분배 이력이 없는 종목일 수 있음 -> 빈 Series 로 두되,
                # 상위(distribution_service)에서 "분배 이력 없음" 으로 처리
                s.index = pd.DatetimeIndex([], name="date")
                return s
            s.index = _to_daily_index(pd.DatetimeIndex(s.index))
            s.name = "distribution"
            return s

        alls = cache.get_or_set(key, config.CACHE_TTL_DISTRIBUTION_SECONDS, _load_all)
        mask = (alls.index >= pd.Timestamp(start)) & (alls.index <= pd.Timestamp(end))
        return alls.loc[mask]

    # ---------------------------------------------------------------
    def get_splits(self, ticker: str, start: date, end: date) -> pd.Series:
        _require_yf()
        key = f"us:split:{ticker}"

        def _load_all() -> pd.Series:
            s = yf.Ticker(ticker).splits
            if s is None or len(s) == 0:
                return pd.Series(dtype="float64", index=pd.DatetimeIndex([], name="date"),
                                 name="split")
            s = s.copy()
            s.index = _to_daily_index(pd.DatetimeIndex(s.index))
            s.name = "split"
            return s

        alls = cache.get_or_set(key, config.CACHE_TTL_PRICE_SECONDS, _load_all)
        if len(alls) == 0:
            return alls
        mask = (alls.index >= pd.Timestamp(start)) & (alls.index <= pd.Timestamp(end))
        return alls.loc[mask]

    # ---------------------------------------------------------------
    def get_info(self, ticker: str) -> dict:
        """상세 패널용 부가 정보. 실패해도 빈 dict (핵심 계산에는 미사용)."""
        _require_yf()
        key = f"us:info:{ticker}"

        def _load() -> dict:
            out: dict = {}
            try:
                fi = yf.Ticker(ticker).fast_info
                for k in ("lastPrice", "currency", "yearHigh", "yearLow", "yearChange"):
                    try:
                        out[k] = fi.get(k) if hasattr(fi, "get") else fi[k]
                    except Exception:
                        pass
            except Exception:
                pass
            return out

        try:
            return cache.get_or_set(key, config.CACHE_TTL_LATEST_PRICE_SECONDS, _load)
        except Exception:
            return {}


# ---- 환율(fx_provider 가 재사용) : USD/KRW via yfinance --------------------
def fetch_usdkrw_history(start: date, end: date) -> pd.Series:
    _require_yf()
    key = f"fx:usdkrw:hist:{start}:{end}"

    def _load() -> pd.Series:
        raw = yf.Ticker(config.FX_PAIR_USDKRW).history(
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
            auto_adjust=False,
        )
        if raw is None or raw.empty or "Close" not in raw.columns:
            raise DataUnavailable(f"{start}~{end} 구간의 USD/KRW 환율 데이터를 가져오지 못했습니다.")
        raw = raw.dropna(subset=["Close"])
        if raw.empty:
            raise DataUnavailable(f"{start}~{end} 구간에 유효한 USD/KRW 환율이 없습니다.")
        s = pd.Series(raw["Close"].to_numpy(), index=_to_daily_index(raw.index), name="usdkrw")
        return s

    return cache.get_or_set(key, config.CACHE_TTL_FX_SECONDS, _load)


def fetch_usdkrw_latest() -> FxQuote:
    today = date.today()
    s = fetch_usdkrw_history(today - timedelta(days=10), today)
    last_dt = s.index.max()
    return FxQuote(pair="USD/KRW", rate=float(s.loc[last_dt]), as_of=last_dt.date(),
                   source="yfinance")
