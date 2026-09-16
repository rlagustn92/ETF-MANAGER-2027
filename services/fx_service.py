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

import math
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


def _checked(rate: object, as_of, source: str) -> FxResult:
    """조회는 됐는데 값이 말이 안 되면 '조회 실패'와 같은 길로 보냅니다.

    왜 이렇게 하나
    --------------
    환율 **조회 실패**는 앱이 이미 잘 다룹니다 — 경고를 띄우고 화면은 삽니다.
    무방비였던 건 "조회는 성공했는데 값이 0" 같은 경우입니다. 그 값이 to_krw()
    까지 가면 예외가 나고 **미국 종목을 담은 모든 사용자의 화면이 죽습니다.**
    게다가 그 값이 캐시에 한 번 들어가면 캐시가 만료될 때까지 계속 죽습니다.

    새 화면을 만들 이유가 없습니다. 이미 잘 도는 실패 경로에 합류시키면 됩니다.
    1달러가 0원이거나 마이너스인 상황은 존재하지 않으므로 잃는 것도 없습니다.
    """
    try:
        value = float(rate)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        value = float("nan")
    if not math.isfinite(value) or value <= 0:
        return FxResult(rate=None, as_of=None, source="", ok=False,
                        message=f"USD/KRW 환율 값이 올바르지 않습니다({rate!r}). "
                                f"잠시 뒤 다시 시도해 주세요.")
    return FxResult(rate=value, as_of=as_of, source=source, ok=True)


def current_usdkrw() -> FxResult:
    try:
        q = fx_provider.get_latest_rate()
        return _checked(q.rate, q.as_of, q.source)
    except DataUnavailable as e:
        return FxResult(rate=None, as_of=None, source="", ok=False, message=str(e))


def usdkrw_on(d: date) -> FxResult:
    try:
        q = fx_provider.get_rate_on(d)
        return _checked(q.rate, q.as_of, q.source)
    except DataUnavailable as e:
        return FxResult(rate=None, as_of=None, source="", ok=False, message=str(e))
