"""
data/providers/kr_provider.py  --  한국 주식/ETF 데이터 (FinanceDataReader)
=========================================================================

설치 확인 (2026-09, 실행 검증 완료):
    finance-datareader 0.9.202
    fdr.DataReader("005930", start, end) -> columns: Open, High, Low, Close, Volume, Change
        (한국 종목은 Adj Close 열이 없음. FDR 의 한국 종가는 수정주가(분할/액면분할 반영) 기준)
    fdr.StockListing("KRX")     -> Code, Name, Market, ... (검색/목록용)
    fdr.StockListing("ETF/KR")  -> Symbol, Name, Category, NAV, ...

분배금(배당)
------------
FinanceDataReader 는 한국 종목의 분배금 시계열을 직접 제공하지 않습니다.
보조로 yfinance 의 한국 심볼(예: 005930.KS / 035420.KQ)을 시도하고,
그래도 없으면 DataUnavailable 를 던집니다. (추정값 사용 금지 -- 인수인계서 44, 117)
사용자는 UI 에서 "직접 입력" 으로 최근 12개월 주당 분배금을 넣을 수 있습니다. (인수인계서 39)
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

import config
from data.providers import cache
from data.providers.base import (
    DataUnavailable,
    HISTORY_CLOSE_COL,
    MarketDataProvider,
    PriceQuote,
)

try:
    import FinanceDataReader as fdr
except Exception as _e:  # pragma: no cover
    fdr = None
    _IMPORT_ERROR = _e
else:
    _IMPORT_ERROR = None

try:
    import yfinance as yf
except Exception:  # pragma: no cover
    yf = None


def _require_fdr() -> None:
    if fdr is None:
        raise DataUnavailable(
            f"FinanceDataReader 를 불러올 수 없습니다: {_IMPORT_ERROR}. "
            f"'pip install finance-datareader' 를 확인하세요."
        )


def _to_daily_index(idx) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(pd.to_datetime([getattr(d, "date", lambda: d)() for d in idx]),
                            name="date")


def _yf_symbols(ticker: str) -> list[str]:
    """한국 6자리 코드 -> yfinance 심볼 후보 (KOSPI .KS, KOSDAQ .KQ).

    KRX 코드는 6자리면 순수 숫자(대부분의 주식/ETF)뿐 아니라 ETN 등 일부 상품처럼
    숫자+영문 조합("0219E0" 같은)도 있습니다. 이전엔 isdigit() 조건 때문에 그런
    코드는 .KS/.KQ 접미사를 안 붙여서 분배금 조회가 실패했습니다(실제 버그로 확인:
    "0219E0" 는 yfinance 에 "0219E0.KS" 로는 실제 배당 데이터가 존재함).
    길이만 6자리면 숫자/영문 상관없이 접미사를 시도합니다.
    """
    t = str(ticker).strip()
    if len(t) == 6:
        return [f"{t}.KS", f"{t}.KQ"]
    return [t]


class KRDataProvider(MarketDataProvider):
    name = "FinanceDataReader"

    # ---------------------------------------------------------------
    def get_price_history(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        _require_fdr()
        key = f"kr:hist:{ticker}:{start}:{end}"

        def _load() -> pd.DataFrame:
            raw = fdr.DataReader(str(ticker), start.isoformat(), end.isoformat())
            if raw is None or raw.empty or "Close" not in raw.columns:
                raise DataUnavailable(
                    f"[{ticker}] {start}~{end} 구간의 한국 가격 데이터를 가져오지 못했습니다."
                )
            raw = raw.dropna(subset=["Close"])
            raw = raw[raw["Close"] > 0]
            if raw.empty:
                raise DataUnavailable(f"[{ticker}] {start}~{end} 구간에 유효한 종가가 없습니다.")
            df = pd.DataFrame(index=_to_daily_index(raw.index))
            df[HISTORY_CLOSE_COL] = raw["Close"].to_numpy()
            df.attrs["currency"] = "KRW"
            df.attrs["source"] = self.name
            df.attrs["note"] = "FDR 한국 종가 = 수정주가(분할 반영)"
            return df

        return cache.get_or_set(key, config.CACHE_TTL_PRICE_SECONDS, _load)

    # ---------------------------------------------------------------
    def get_latest_price(self, ticker: str) -> PriceQuote:
        key = f"kr:last:{ticker}"

        def _load() -> PriceQuote:
            today = date.today()
            df = self.get_price_history(ticker, today - timedelta(days=14), today)
            last_dt = df.index.max()
            return PriceQuote(
                ticker=str(ticker),
                price=float(df.loc[last_dt, HISTORY_CLOSE_COL]),
                currency="KRW",
                as_of=last_dt.date(),
                source=self.name,
            )

        return cache.get_or_set(key, config.CACHE_TTL_LATEST_PRICE_SECONDS, _load)

    # ---------------------------------------------------------------
    def get_distributions(self, ticker: str, start: date, end: date) -> pd.Series:
        key = f"kr:div:{ticker}"

        def _load_all() -> pd.Series:
            if yf is not None:
                for sym in _yf_symbols(ticker):
                    try:
                        s = yf.Ticker(sym).dividends
                    except Exception:
                        s = None
                    if s is not None and len(s) > 0:
                        s = s.copy()
                        s.index = _to_daily_index(pd.DatetimeIndex(s.index))
                        s.name = "distribution"
                        s.attrs["source"] = f"yfinance:{sym}"
                        return s
            raise DataUnavailable(
                f"[{ticker}] 한국 종목의 분배금 데이터를 자동으로 확인할 수 없습니다. "
                f"상세 패널에서 '직접 입력' 을 사용하세요."
            )

        alls = cache.get_or_set(key, config.CACHE_TTL_DISTRIBUTION_SECONDS, _load_all)
        mask = (alls.index >= pd.Timestamp(start)) & (alls.index <= pd.Timestamp(end))
        return alls.loc[mask]

    # ---------------------------------------------------------------
    def get_splits(self, ticker: str, start: date, end: date) -> pd.Series:
        empty = pd.Series(dtype="float64", index=pd.DatetimeIndex([], name="date"), name="split")
        key = f"kr:split:{ticker}"

        def _load_all() -> pd.Series:
            if yf is not None:
                for sym in _yf_symbols(ticker):
                    try:
                        s = yf.Ticker(sym).splits
                    except Exception:
                        s = None
                    if s is not None and len(s) > 0:
                        s = s.copy()
                        s.index = _to_daily_index(pd.DatetimeIndex(s.index))
                        s.name = "split"
                        return s
            # FDR 한국 종가는 이미 수정주가이므로 분할 재조정이 불필요.
            # 분할 이력을 알 수 없을 때는 빈 Series(정상)로 반환.
            return empty

        alls = cache.get_or_set(key, config.CACHE_TTL_PRICE_SECONDS, _load_all)
        if len(alls) == 0:
            return alls
        mask = (alls.index >= pd.Timestamp(start)) & (alls.index <= pd.Timestamp(end))
        return alls.loc[mask]

    # ---------------------------------------------------------------
    def get_info(self, ticker: str) -> dict:
        return {}
