"""
services/fx_service.py  --  환율 정책 계층 (인수인계서 50, 51)
==========================================================

"환율 API 가 바뀌었는데 어디를 고치지?" -> data/providers/fx_provider.py
"현재/과거 환율을 어떻게 쓰는지 규칙을 바꾸고 싶다" -> 이 파일

규칙
----
- 현재 포트폴리오 계산: 현재(가장 최근) USD/KRW
- 백테스트:            해당 매수 기준일의 USD/KRW (과거 환율)
  => "과거 주가 + 현재 환율" 조합은 절대 사용하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from data.providers import fx_provider
from data.providers.base import DataUnavailable


@dataclass
class FxResult:
    rate: float | None       # 1 USD = rate KRW  (None => 데이터 없음)
    as_of: date | None
    source: str
    ok: bool
    message: str = ""


def current_usdkrw() -> FxResult:
    try:
        q = fx_provider.get_latest_rate()
        return FxResult(rate=q.rate, as_of=q.as_of, source=q.source, ok=True)
    except DataUnavailable as e:
        return FxResult(rate=None, as_of=None, source="", ok=False, message=str(e))


def usdkrw_on(d: date) -> FxResult:
    try:
        q = fx_provider.get_rate_on(d)
        return FxResult(rate=q.rate, as_of=q.as_of, source=q.source, ok=True)
    except DataUnavailable as e:
        return FxResult(rate=None, as_of=None, source="", ok=False, message=str(e))
