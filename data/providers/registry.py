"""
data/providers/registry.py  --  시장 -> provider 매핑 한 곳 (교체 지점, 인수인계서 107-3)
=====================================================================================

provider 를 교체하려면 이 파일만 수정하면 됩니다.
services / UI 는 get_provider(market) 만 호출합니다.
"""

from __future__ import annotations

from functools import lru_cache

from models.security import MARKET_KR, MARKET_US
from data.providers import alpaca_provider
from data.providers.base import MarketDataProvider
from data.providers.us_composite import USCompositeProvider
from data.providers.us_provider import USDataProvider
from data.providers.kr_provider import KRDataProvider


@lru_cache(maxsize=None)
def get_provider(market: str) -> MarketDataProvider:
    m = (market or "").upper()
    if m == MARKET_US:
        # Alpaca 키가 있으면 둘을 섞어서 씁니다 (어느 쪽을 먼저 쓸지는
        # us_composite.py 의 설명 참고: 잦은 호출은 Alpaca, 과거 깊이가 필요한 건 yfinance).
        # 키가 없으면(개인 PC 등) 기존처럼 yfinance 단독으로 동작합니다.
        if alpaca_provider.is_configured():
            return USCompositeProvider(alpaca_provider.AlpacaDataProvider(), USDataProvider())
        return USDataProvider()
    if m == MARKET_KR:
        # 한국 종목은 Alpaca 에 없습니다(invalid symbol). FinanceDataReader 유지.
        return KRDataProvider()
    raise ValueError(f"알 수 없는 시장(market): {market!r} (US 또는 KR)")


def reset_cache() -> None:
    """키를 넣고 뺐을 때 등 provider 선택을 다시 하도록 (테스트/설정 변경용)."""
    get_provider.cache_clear()
