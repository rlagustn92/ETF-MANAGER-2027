"""
models/numbers.py  --  바깥에서 들어온 숫자를 계산에 넣기 전에 거르는 곳
=======================================================================

왜 이 파일이 따로 있나
----------------------
전술 JSON, 브라우저 컴포넌트, 외부 시세 API — **우리가 안 만든 값**이 들어오는
입구가 여러 곳입니다. 그런 값 하나가 계산까지 흘러가면 화면 전체가 죽습니다.

    "target_weight": 1e400   ->  math.floor(inf)   -> OverflowError
    "target_weight": NaN     ->  math.floor(nan)   -> ValueError
    "target_weight": "많이"   ->  f"{x:.2f}"        -> ValueError

셋 다 증상은 같습니다. **빨간 에러 화면 + 새로고침해도 그대로.**
그래서 거르는 규칙을 각자 따로 쓰지 않고 여기 한 군데에 모읍니다.

쓰는 방법은 두 가지입니다.

    is_finite_number(v)   "이 값이 멀쩡한가?" — 사용자에게 알려주려고 물어볼 때
    safe_float(v, ...)    "어떻게든 쓸 수 있는 숫자로" — 절대 안 죽어야 할 때

안내(is_finite_number)와 안전망(safe_float)은 **둘 다** 있어야 합니다.
안내만 하면 다른 입구로 들어온 값에 죽고, 안전망만 두면 사용자는 자기 비중이
왜 0이 됐는지 영영 모릅니다.
"""

from __future__ import annotations

import math


def is_finite_number(value: object) -> bool:
    """계산에 그대로 써도 되는 숫자인가.

    - `True`/`False` 는 숫자로 치지 않습니다. `float(True)` 가 1.0 이라
      `"target_weight": true` 가 조용히 **100%** 가 되어버립니다.
    - `"0.3"` 처럼 숫자로 적힌 문자열은 **통과**시킵니다. 예전에 손으로 만든
      전술 파일에 실제로 들어 있고, 뜻이 분명해서 거절할 이유가 없습니다.
    """
    if isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False


def safe_float(value: object, *, default: float = 0.0,
               minimum: float | None = None, maximum: float | None = None) -> float:
    """무슨 값이 오든 계산해도 안전한 float 하나를 돌려줍니다. 절대 예외를 던지지 않습니다.

    숫자가 아니거나 NaN·무한대면 `default` 를 씁니다.
    `minimum`/`maximum` 을 주면 그 범위로 자릅니다.
    """
    if not is_finite_number(value):
        return float(default)
    out = float(value)  # type: ignore[arg-type]
    if minimum is not None:
        out = max(float(minimum), out)
    if maximum is not None:
        out = min(float(maximum), out)
    return out
