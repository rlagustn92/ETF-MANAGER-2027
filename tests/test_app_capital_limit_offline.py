"""app.py 의 '초기자본 초과 방지' 기능 end-to-end 테스트 (네트워크 없음).

기본값(strict_capital_limit=True)에서는 목표비중 슬라이더/직접입력을 다른 종목과의
합계가 100% 를 넘도록 조작해도, 실제로는 남은 여유만큼으로 자동 조정되고 경고가
떠야 합니다. 헤더의 "초기자본 초과 허용" 토글을 켜면 제한 없이 입력할 수 있어야 합니다.
"""

from __future__ import annotations

import pathlib

from streamlit.testing.v1 import AppTest

from models.portfolio import Portfolio
from models.security import Security

APP_PATH = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")


def _seed_portfolio() -> Portfolio:
    p = Portfolio(name="t", initial_capital_krw=10_000_000)
    p.add(Security(market="US", ticker="A", currency="USD", target_weight=0.70))
    p.add(Security(market="US", ticker="B", currency="USD", target_weight=0.0))
    return p


def test_slider_is_clamped_by_default_when_exceeding_remaining_budget(market):
    market.set_fx(rate=1_000.0)
    market.set_us({"A": {"currency": "USD", "latest": 100.0},
                   "B": {"currency": "USD", "latest": 100.0}})
    p = _seed_portfolio()
    b_id = p.securities[1].id

    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["portfolio"] = p
    at.session_state["selected_id"] = b_id
    at.run()
    assert not at.exception
    assert p.strict_capital_limit is True   # 기본값 확인

    slider = [s for s in at.slider if s.label == "살(BUY) 비율 (%)"][0]
    slider.set_value(90.0).run()   # A 가 이미 70% 이므로 B 는 최대 30%
    assert not at.exception

    slider2 = [s for s in at.slider if s.label == "살(BUY) 비율 (%)"][0]
    assert slider2.value == 30.0

    warnings = [w.value for w in at.warning]
    assert any("자동 조정" in w for w in warnings), warnings


def test_toggle_off_allows_exceeding_budget(market):
    market.set_fx(rate=1_000.0)
    market.set_us({"A": {"currency": "USD", "latest": 100.0},
                   "B": {"currency": "USD", "latest": 100.0}})
    p = _seed_portfolio()
    b_id = p.securities[1].id

    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["portfolio"] = p
    at.session_state["selected_id"] = b_id
    at.run()

    toggle = [t for t in at.toggle if t.label == "시드보다 더 담기 허용"][0]
    toggle.set_value(True).run()
    assert not at.exception
    assert at.session_state["portfolio"].strict_capital_limit is False

    slider = [s for s in at.slider if s.label == "살(BUY) 비율 (%)"][0]
    slider.set_value(90.0).run()
    assert not at.exception

    slider2 = [s for s in at.slider if s.label == "살(BUY) 비율 (%)"][0]
    assert slider2.value == 90.0   # 이제 잘리지 않음 (합계 160% 허용)

    metrics = {m.label: m.value for m in at.metric}
    assert metrics["살(BUY) 비율"] == "90.00%"
