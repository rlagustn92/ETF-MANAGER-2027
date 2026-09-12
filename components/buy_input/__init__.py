"""
components/buy_input/  --  "얼마어치 살까? / 몇 주 살까?" 입력 카드 (토스증권 풍)
==============================================================================

Streamlit 기본 입력칸(st.text_input / st.number_input)은 엔터를 누르거나 칸 밖을
클릭해야만 값이 서버로 전달됩니다. 그래서 "타이핑하는 동안 바로 계산 결과가 보였으면
좋겠다"(사용자 요청)를 기본 위젯으로는 만들 수 없어, 전술판과 같은 방식의 커스텀
컴포넌트로 만들었습니다.

동작
----
- 미리보기("= 103주 · 실제 ₩30,900,000 ...")는 브라우저 안에서 바로 계산해 그립니다.
  서버를 거치지 않으므로 엔터 없이 글자를 칠 때마다 즉시 갱신됩니다.
- 실제 값(금액/수량)은 잠깐 타이핑을 멈추거나(0.45초) 엔터/포커스아웃 시 서버로
  전달되어 살(BUY) 비율에 반영됩니다.
- 단위(원 / 주)는 입력칸 안에 붙어 있어 달러인지 원화인지 헷갈리지 않습니다.

미리보기 계산식은 services/calculation_service.py 의 정수/소수점 매수 계산과 같은
규칙(정수 매수는 내림)을 씁니다. 두 값이 어긋나면 안 되므로,
tests/test_app_amount_input_offline.py 가 "미리보기 주수 == 실제 계산 주수" 를 검증합니다.

반환값
------
dict {
  "source": "amount" | "qty",   # 마지막으로 사용자가 건드린 칸
  "amount": float,              # 원화 금액
  "qty": float,                 # 주식 수
  "nonce": int,                 # 같은 값을 중복 적용하지 않기 위한 카운터
}
또는 최초 렌더 시 None.
"""

from __future__ import annotations

import os

import streamlit.components.v1 as components

_FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")

_component_func = components.declare_component("etf_buy_input", path=_FRONTEND_DIR)


def buy_input(
    *,
    amount: float,
    qty: float,
    price_krw: float | None,
    price_native: float | None,
    currency: str,
    fx_rate: float | None = None,
    fractional: bool = False,
    price_warning: str = "",
    echo: int = 0,
    key: str | None = None,
):
    """금액/수량 입력 카드.

    amount/qty 는 "서버가 알고 있는 현재 값"입니다. 사용자가 입력 중이 아닐 때나
    서버가 값을 보정했을 때(시드 한도 초과로 잘림 등)만 입력칸에 반영됩니다.

    echo: 서버가 마지막으로 처리한 입력의 번호. Streamlit 은 넘겨주는 값이 직전과
      똑같으면 컴포넌트를 다시 그리지 않습니다. 그러면 "시드보다 큰 금액을 두 번
      연속 입력" 같은 경우에 보정된 값이 입력칸에 반영되지 못하므로, 입력이 있을
      때마다 바뀌는 이 값을 함께 넘겨서 항상 다시 그려지게 합니다.
    """
    return _component_func(
        amount=float(amount or 0.0),
        qty=float(qty or 0.0),
        price_krw=price_krw,
        price_native=price_native,
        currency=currency,
        fx_rate=fx_rate,
        fractional=bool(fractional),
        price_warning=price_warning,
        echo=int(echo),
        key=key,
        default=None,
    )
