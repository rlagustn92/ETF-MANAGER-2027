"""종목 제거 동작 테스트 (네트워크 없음).

사용자가 "예시를 불러온 뒤 종목을 지웠는데 안 지워진다"고 알려와서 점검하며 만든
테스트입니다. 기본 제거 동작은 정상이었지만, 그 과정에서 다음 두 가지를 고쳤고
여기서 지켜집니다.

1) 지운 종목이 다시 '선택된 종목'으로 되살아나지 않을 것
   전술판 컴포넌트는 마지막으로 클릭한 종목 id 를 계속 들고 있어서, 지운 뒤에도 그
   값이 남아 있습니다. 확인 없이 쓰면 이미 없는 종목이 선택된 상태가 됩니다.
2) 제거 버튼에 어떤 종목이 지워지는지 이름이 나올 것
   "종목 제거" 라고만 있으면, 선택이 바뀌는 도중에 누를 때 엉뚱한 종목이 지워져도
   알아채기 어렵습니다.
"""

from __future__ import annotations

import pathlib

from streamlit.testing.v1 import AppTest

import presets
from models.portfolio import Portfolio
from models.security import Security

APP_PATH = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")


def _market_for_presets(market):
    market.set_fx(rate=1_400.0)
    market.set_us({i.ticker: {"currency": "USD", "latest": 100.0}
                   for p in presets.PRESETS for i in p.items if i.market == "US"})
    market.set_kr({i.ticker: {"currency": "KRW", "latest": 10_000.0}
                   for p in presets.PRESETS for i in p.items if i.market == "KR"})


def _remove_button(at):
    return [b for b in at.button if b.label.startswith("🗑")][0]


def test_remove_button_names_the_security_it_deletes(market):
    _market_for_presets(market)
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["portfolio"] = presets.build_portfolio(presets.AGGRESSIVE)
    at.run()

    target = at.session_state["portfolio"].securities[-1]   # KODEX 200커버드콜액티브
    at.session_state["selected_id"] = target.id
    at.run()

    assert _remove_button(at).label == f"🗑 {target.display_name} 제거"


def test_removing_a_preset_security_actually_removes_it(market):
    """사용자가 겪은 상황 그대로: 공격배당형 -> KODEX 200커버드콜액티브 제거."""
    _market_for_presets(market)
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["portfolio"] = presets.build_portfolio(presets.AGGRESSIVE)
    at.run()

    victim = next(s for s in at.session_state["portfolio"].securities
                  if s.ticker == "0219E0")
    at.session_state["selected_id"] = victim.id
    at.run()

    _remove_button(at).click().run()
    assert not at.exception

    tickers = [s.ticker for s in at.session_state["portfolio"].securities]
    assert "0219E0" not in tickers
    assert len(tickers) == len(presets.AGGRESSIVE.items) - 1
    # 지운 종목이 선택 상태로 남아 있으면 안 된다
    assert at.session_state["selected_id"] is None


def test_removing_several_in_a_row_works(market):
    _market_for_presets(market)
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["portfolio"] = presets.build_portfolio(presets.AGGRESSIVE)
    at.run()

    for _ in range(3):
        remaining = at.session_state["portfolio"].securities
        at.session_state["selected_id"] = remaining[0].id
        at.run()
        _remove_button(at).click().run()
        assert not at.exception

    assert len(at.session_state["portfolio"].securities) == len(presets.AGGRESSIVE.items) - 3


def test_removing_frees_the_pitch_slot_and_widget_state(market):
    """지운 종목의 슬롯과 입력칸 상태가 남아 있으면 다음 종목에 영향을 줍니다."""
    market.set_fx(rate=1_000.0)
    market.set_us({"A": {"currency": "USD", "latest": 100.0},
                   "B": {"currency": "USD", "latest": 100.0}})
    p = Portfolio(name="t", initial_capital_krw=10_000_000)
    p.add(Security(market="US", ticker="A", currency="USD", target_weight=0.30))
    p.add(Security(market="US", ticker="B", currency="USD", target_weight=0.20))
    a_id, a_slot = p.securities[0].id, p.securities[0].slot

    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["portfolio"] = p
    at.session_state["selected_id"] = a_id
    at.run()
    assert f"wsel_{a_id}" in at.session_state          # 편집 위젯 상태가 생겼다가

    _remove_button(at).click().run()
    assert not at.exception

    assert f"wsel_{a_id}" not in at.session_state      # 지울 때 같이 정리되어야 한다
    assert f"buy_{a_id}" not in at.session_state
    assert a_slot not in at.session_state["portfolio"].used_slots()
