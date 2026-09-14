"""
formatting.py  --  화면에 숫자를 어떻게 적을지 (한 곳에서 관리)
================================================================

원래 app.py 안에 있던 함수들입니다. app.py 는 Streamlit 실행 파일이라 그냥
import 할 수가 없어서(불러오는 순간 화면을 그리기 시작합니다) 테스트를 붙일 수
없었는데, **돈을 잘못 적으면 사용자가 그대로 오해**하는 부분이라 따로 떼어냈습니다.
호출하는 쪽 이름은 그대로여서 app.py 코드는 바뀌지 않습니다.
"""

from __future__ import annotations

import config


def won(x) -> str:
    """기본 원화 표기. 예: ₩45,000,000"""
    if x is None:
        return config.NO_DATA_TEXT
    return f"₩{x:,.0f}"


def pct(x, digits: int = 2) -> str:
    if x is None:
        return config.NO_DATA_TEXT
    return f"{x:.{digits}f}%"


def won_short(x) -> str:
    """캡처 이미지처럼 자리가 좁은 곳에서 쓰는 짧은 금액 표기.

    "₩45,000,000" 은 이미지 안에서 너무 길고 한눈에 안 읽힙니다.
    한국에서 실제로 말하는 단위(만/억)로 줄입니다.
        45,000,000 -> 4,500만     187,000 -> 18.7만     123,400,000 -> 1.23억

    만 단위에서 100만 미만은 소수 한 자리를 남깁니다("18.7만").
    안 그러면 월 분배금처럼 작은 금액이 죄다 "19만" 으로 뭉개져서
    종목끼리 비교가 안 됩니다.
    """
    if x is None:
        return config.NO_DATA_TEXT
    v = float(x)
    sign = "-" if v < 0 else ""
    v = abs(v)
    if v >= 100_000_000:
        # rstrip 은 소수점 아래만 건드립니다("10.00" -> "10." -> "10").
        return f"{sign}{v / 100_000_000:,.2f}".rstrip("0").rstrip(".") + "억"
    if v >= 10_000:
        man = v / 10_000
        return f"{sign}{man:,.0f}만" if man >= 100 else f"{sign}{man:,.1f}만"
    return f"{sign}{v:,.0f}원"


def native_amt(x, currency: str, usd_digits: int = 2) -> str:
    """종목의 "원래 통화" 기준 금액(가격/분배금 등) 표시. 원화는 소수점을 쓰지 않습니다.

    한국 원화는 실질적으로 1원 미만 단위가 없어 소수점이 의미가 없으므로 정수로,
    달러 등 다른 통화는 usd_digits 자리(기본 2자리)까지 보여줍니다.
    (환율 "비율" 자체는 여기 대상이 아닙니다 -- USD/KRW 환율 표시는 그대로 소수점 유지)
    """
    if x is None:
        return config.NO_DATA_TEXT
    if currency == "KRW":
        return f"{x:,.0f}"
    return f"{x:,.{usd_digits}f}"
