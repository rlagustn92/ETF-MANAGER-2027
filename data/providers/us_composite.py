"""
data/providers/us_composite.py  --  미국 종목: 호출 성격에 따라 소스를 나눠 씁니다.

왜 나눠 쓰나
------------
두 소스의 장단점이 정반대입니다.

              | Alpaca (무료)                  | yfinance
  요청 한도    | API 키 기준 (여러 명이 써도 안전) | 서버 IP 기준 (배포 시 막힐 수 있음)
  과거 깊이    | **약 2020년 중반까지만**         | 10년 이상
  배당 데이터  | 있음 (corporate actions)        | 있음

그래서 호출 빈도와 필요한 성질에 맞춰 배분합니다.

  · 최신가, 분배금  -> **Alpaca 우선** (화면을 그릴 때마다 종목 수만큼 호출되는 잦은 요청.
                       여기가 막히면 앱의 핵심 숫자가 통째로 비므로 한도에 강한 쪽을 씀)
  · 가격 히스토리    -> **yfinance 우선** (백테스트에서만 쓰는 드문 요청이고, 대신 과거가
                       깊어야 함. Alpaca 를 먼저 쓰면 2020년 이전 백테스트가 막힘)
  · 분할           -> yfinance 우선 (히스토리와 같은 구간을 다루므로 짝을 맞춤)

어느 쪽이든 실패하면 자동으로 반대쪽으로 넘어갑니다. 따라서 한 소스가 통째로
막혀도 앱은 계속 동작합니다. 출처는 PriceQuote.source / DataFrame.attrs["source"] 에
그대로 남아 화면에 표시됩니다(출처를 속이지 않음).
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from data.providers.base import MarketDataProvider, PriceQuote
from data.providers.fallback_provider import FallbackProvider


class USCompositeProvider(MarketDataProvider):
    def __init__(self, alpaca: MarketDataProvider, yahoo: MarketDataProvider):
        # 잦은 호출: 한도에 강한 Alpaca 를 앞에
        self._live = FallbackProvider(alpaca, yahoo)
        # 드물지만 과거가 깊어야 하는 호출: yfinance 를 앞에
        self._history = FallbackProvider(yahoo, alpaca)
        self.name = f"{alpaca.name}+{yahoo.name}"

    def get_latest_price(self, ticker: str) -> PriceQuote:
        return self._live.get_latest_price(ticker)

    def get_distributions(self, ticker: str, start: date, end: date) -> pd.Series:
        return self._live.get_distributions(ticker, start, end)

    def get_price_history(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        return self._history.get_price_history(ticker, start, end)

    def get_splits(self, ticker: str, start: date, end: date) -> pd.Series:
        return self._history.get_splits(ticker, start, end)

    def get_info(self, ticker: str) -> dict:
        return self._live.get_info(ticker)
