"""
data/providers/base.py  --  데이터 제공자 공통 인터페이스 (Adapter, 인수인계서 49, 107-3)
==========================================================================================

구조:   UI  ->  Service  ->  MarketDataProvider(인터페이스)  ->  Yahoo / KRX / 기타

향후 특정 provider(yfinance 등)에 문제가 생겨도 이 인터페이스만 유지하면
services / UI 를 건드리지 않고 provider 파일만 교체할 수 있습니다.

데이터가 없을 때의 절대 원칙 (인수인계서 38, 52, 117, 123)
---------------------------------------------------------
- 추측값을 만들지 않는다.
- 다른 종목/유사 종목 값을 대신 쓰지 않는다.
- DataUnavailable 예외를 던지고, 상위 서비스가 "데이터 없음" 으로 표시한다.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from datetime import date

import pandas as pd


class DataUnavailable(Exception):
    """가격/환율/분배금/분할 데이터를 확인할 수 없을 때 발생.

    message 는 그대로 사용자에게 보여줄 수 있는 한국어 문장으로 작성합니다.
    """


@dataclass
class PriceQuote:
    ticker: str
    price: float             # 해당 종목의 "원래 통화" 기준 1주 가격 (실제 종가 개념)
    currency: str            # "USD" | "KRW"
    as_of: date              # 이 가격의 데이터 기준일 (일별 종가)
    source: str              # "yfinance" | "FinanceDataReader" | "manual"


@dataclass
class FxQuote:
    pair: str                # "USD/KRW"
    rate: float              # 1 USD = rate KRW
    as_of: date
    source: str


# 가격 히스토리 DataFrame 규약
# ---------------------------------
# index : pandas.DatetimeIndex (tz 제거, 날짜만)  -- 이름 "date"
# 열    : "close"      매수/평가에 쓰는 종가 계열.
#                      * 미국(yfinance, auto_adjust=False): 분할은 소급 반영, 배당은 미반영
#                      * 한국(FinanceDataReader): 수정주가(분할 반영)
#                      => 두 소스 모두 "분할 반영 / 배당 미반영" 으로 일관됨.
#         "adj_close"  조정종가(배당까지 반영, 참고용). 없을 수 있음.
# attrs : df.attrs["currency"], df.attrs["source"]
#
# 백테스트는 이 "close" 계열을 매수/평가에 동일하게 사용하므로 분할 왜곡이 없습니다.
# 보유수량에 분할비율을 추가로 곱하지 않습니다. (인수인계서 62~65, 112)
HISTORY_CLOSE_COL = "close"
HISTORY_ADJCLOSE_COL = "adj_close"


class MarketDataProvider(abc.ABC):
    """시장별(미국/한국) 데이터 제공자가 구현해야 하는 인터페이스."""

    name: str = "base"

    @abc.abstractmethod
    def get_latest_price(self, ticker: str) -> PriceQuote:
        """가장 최근 "일별 종가" 를 반환. 없으면 DataUnavailable."""

    @abc.abstractmethod
    def get_price_history(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        """[start, end] 구간의 일별 가격 히스토리. 위 DataFrame 규약을 따름.

        구간에 데이터가 전혀 없으면 DataUnavailable.
        """

    @abc.abstractmethod
    def get_distributions(self, ticker: str, start: date, end: date) -> pd.Series:
        """[start, end] 구간의 주당 현금 분배금(배당) 시계열.

        - 값: 지급일 기준 주당 분배금 (해당 종목 통화)
        - 데이터 소스가 분배금을 제공하지 않으면 DataUnavailable
          (0 으로 채우지 않는다 -- 인수인계서 36, 38)
        """

    @abc.abstractmethod
    def get_splits(self, ticker: str, start: date, end: date) -> pd.Series:
        """[start, end] 구간의 주식분할 비율 시계열. 분할 이력이 없으면 빈 Series 반환(정상)."""

    def get_listing_first_date(self, ticker: str) -> date | None:
        """가능하면 상장(데이터 시작) 일자를 반환. 알 수 없으면 None.

        백테스트에서 "시작일이 상장 이전" 인지 판단하는 데 사용. (인수인계서 71)
        기본 구현은 아주 이른 날짜부터 히스토리를 조회해 첫 날짜를 취함.
        """
        try:
            df = self.get_price_history(ticker, date(1990, 1, 1), date.today())
        except DataUnavailable:
            return None
        if df is None or df.empty:
            return None
        return df.index.min().date()
