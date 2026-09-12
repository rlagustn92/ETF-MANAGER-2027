"""
data/providers/fallback_provider.py  --  1순위가 실패하면 2순위로 넘기는 provider

용도: 미국 종목을 Alpaca(키 기준 할당량, 안정적)로 받되, Alpaca 가 못 주는 경우
(키 없음, 한도 초과, 해당 종목 없음 등) **조용히 멈추지 말고** yfinance 로 이어받게 합니다.

배포해서 여러 명이 쓸 때 한쪽 소스가 막히더라도 화면이 "데이터 없음"으로 비지 않게
하는 것이 목적입니다. 어느 쪽에서 온 값인지는 PriceQuote.source / DataFrame.attrs["source"]
에 그대로 남아서 화면에 표시됩니다(출처를 속이지 않음).
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from data.providers.base import DataUnavailable, MarketDataProvider, PriceQuote


class FallbackProvider(MarketDataProvider):
    """primary 를 먼저 쓰고, DataUnavailable 이면 secondary 로 재시도."""

    def __init__(self, primary: MarketDataProvider, secondary: MarketDataProvider):
        self.primary = primary
        self.secondary = secondary
        self.name = f"{primary.name}+{secondary.name}"

    def _try(self, method: str, *args):
        try:
            return getattr(self.primary, method)(*args)
        except DataUnavailable:
            return getattr(self.secondary, method)(*args)

    def get_latest_price(self, ticker: str) -> PriceQuote:
        return self._try("get_latest_price", ticker)

    def get_price_history(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        return self._try("get_price_history", ticker, start, end)

    def get_distributions(self, ticker: str, start: date, end: date) -> pd.Series:
        return self._try("get_distributions", ticker, start, end)

    def get_splits(self, ticker: str, start: date, end: date) -> pd.Series:
        return self._try("get_splits", ticker, start, end)

    def get_info(self, ticker: str) -> dict:
        try:
            return self.primary.get_info(ticker)
        except Exception:
            try:
                return self.secondary.get_info(ticker)
            except Exception:
                return {}
