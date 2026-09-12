"""app.py 화면 표시 서식 테스트 (네트워크 없음, AppTest + market fixture 조합).

사용자 요청: 원화(KRW) 금액은 소수점을 표시하지 않고, 달러(USD) 금액은 기존처럼
소수점을 유지한다. AppTest 는 app.py 를 실제로 실행하므로, tests/conftest.py 의
market 픽스처로 가격/분배금 데이터 계층만 가짜로 바꿔서 네트워크 없이 화면 텍스트를
검증합니다. (종목 검색 자체는 FinanceDataReader 의 실시간 상장목록을 쓰므로,
검색 UI 를 거치지 않고 Portfolio 를 세션 상태에 직접 주입해 완전히 오프라인으로 만듭니다.)
"""

from __future__ import annotations

import pathlib

from streamlit.testing.v1 import AppTest

from models.portfolio import Portfolio
from models.security import Security

APP_PATH = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")


def test_krw_price_has_no_decimals_usd_price_keeps_two(market):
    market.set_fx(rate=1_400.0)
    market.set_kr({"005930": {"currency": "KRW", "latest": 70_500.0}})
    market.set_us({"QQQ": {"currency": "USD", "latest": 716.31}})

    p = Portfolio(name="fmt-test", initial_capital_krw=10_000_000)
    p.add(Security(market="KR", ticker="005930", name="삼성전자",
                   display_name="삼성전자", currency="KRW", target_weight=0.0))
    p.add(Security(market="US", ticker="QQQ", name="Invesco QQQ",
                   currency="USD", target_weight=0.0))
    kr_id = p.securities[0].id
    us_id = p.securities[1].id

    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["portfolio"] = p
    at.session_state["selected_id"] = kr_id
    at.run()
    assert not at.exception

    def all_text() -> str:
        parts = []
        for coll in (at.markdown, at.text, at.caption):
            parts.extend(w.value for w in coll)
        return " ".join(parts)

    krw_text = all_text()
    assert "70,500 KRW" in krw_text, krw_text
    assert "70,500.00" not in krw_text   # 원화에 소수점이 붙으면 안 됨

    at.session_state["selected_id"] = us_id
    at.run()
    assert not at.exception
    usd_text = all_text()
    assert "716.31 USD" in usd_text   # 달러는 소수점 2자리 유지
