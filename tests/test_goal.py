"""'목표까지 얼마 남았나' 테스트.

이 기능의 핵심 설계는 하나입니다 — **목표는 전술이 아니라 사람의 것**.
슬롯을 현재안 → 공격안으로 바꿔도 목표는 그대로 남아야, "공격안으로 바꾸니
41% → 78% 가 되네" 가 보입니다. 목표가 슬롯마다 따로면 그 비교가 성립하지 않습니다.

그리고 여기 나오는 숫자는 **"이렇게 하면 됩니다" 가 아니라 지금 구성 기준 산수**입니다.
"""

from __future__ import annotations

import pathlib

import pytest
from streamlit.testing.v1 import AppTest

import presets
from models.portfolio import Portfolio
from models.security import Security
from services import calculation_service as calc
from services import slot_service

APP_PATH = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")


# =====================================================================
# 산수
# =====================================================================
def test_progress_is_now_over_target():
    assert calc.progress_to_goal(416_496, 1_000_000) == pytest.approx(0.416496)
    assert calc.progress_to_goal(1_200_000, 1_000_000) == pytest.approx(1.2)


@pytest.mark.parametrize("now,target", [(0, 1_000_000), (500_000, 0), (500_000, -1)])
def test_progress_is_zero_when_there_is_nothing_to_compare(now, target):
    assert calc.progress_to_goal(now, target) == 0.0


def test_progress_survives_broken_numbers():
    assert calc.progress_to_goal(float("nan"), 1_000_000) == 0.0
    assert calc.progress_to_goal(500_000, float("nan")) == 0.0
    assert calc.progress_to_goal(float("inf"), 1_000_000) == 0.0


def test_capital_needed_scales_the_seed_proportionally():
    """구성을 그대로 두고 시드만 키우면 분배금도 같은 배로 커집니다."""
    got = calc.capital_needed_for_goal(capital_now_krw=100_000_000,
                                       monthly_now_krw=416_496,
                                       monthly_target_krw=1_000_000)
    assert got == pytest.approx(100_000_000 * (1_000_000 / 416_496), rel=1e-9)


def test_capital_needed_when_you_are_already_there():
    got = calc.capital_needed_for_goal(100_000_000, 1_000_000, 500_000)
    assert got == pytest.approx(50_000_000)


@pytest.mark.parametrize("capital,now,target", [
    (0, 400_000, 1_000_000),          # 시드가 없음
    (100_000_000, 0, 1_000_000),      # 분배금이 0 -- 비례식의 기준이 없음
    (100_000_000, 400_000, 0),        # 목표가 없음
    (float("nan"), 400_000, 1_000_000),
    (100_000_000, float("inf"), 1_000_000),
])
def test_capital_needed_refuses_to_make_a_number_up(capital, now, target):
    """기준이 없는데 숫자를 내놓으면 그건 지어낸 값입니다."""
    assert calc.capital_needed_for_goal(capital, now, target) is None


# =====================================================================
# 화면
# =====================================================================
def _market(market):
    """분배금이 실제로 나오는 가짜 시장.

    ⚠ 분배 이력을 안 넣으면 월 분배금이 0 이 되고, 그러면 목표 계산은 "기준이 없다"
      쪽으로 빠집니다. 목표 기능을 시험하려면 분배금이 반드시 있어야 합니다.
    """
    from tests.conftest import series

    market.set_fx(rate=1_400.0)
    us_pay = series([(f"2026-{m:02d}-15", 0.30) for m in range(1, 10)]
                    + [(f"2025-{m:02d}-15", 0.30) for m in range(10, 13)])
    kr_pay = series([(f"2026-{m:02d}-15", 40.0) for m in range(1, 10)]
                    + [(f"2025-{m:02d}-15", 40.0) for m in range(10, 13)])
    market.set_us({i.ticker: {"currency": "USD", "latest": 100.0, "distributions": us_pay}
                   for p in presets.PRESETS for i in p.items if i.market == "US"})
    market.set_kr({i.ticker: {"currency": "KRW", "latest": 10_000.0, "distributions": kr_pay}
                   for p in presets.PRESETS for i in p.items if i.market == "KR"})


def _goal_box(at):
    return [t for t in at.text_input if t.label.startswith("내 목표")][0]


def _body(at) -> str:
    return " ".join(m.value for m in at.markdown)


def test_no_goal_no_noise(market):
    """목표를 안 적은 사람에게 이런저런 안내를 보여줄 이유가 없습니다."""
    _market(market)
    at = AppTest.from_file(APP_PATH, default_timeout=90)
    at.session_state["portfolio"] = presets.build_portfolio(presets.STABLE)
    at.run()
    assert _goal_box(at).value in ("0", "")
    assert "시드만" not in _body(at)


def test_setting_a_goal_shows_the_seed_you_would_need(market):
    _market(market)
    at = AppTest.from_file(APP_PATH, default_timeout=90)
    at.session_state["portfolio"] = presets.build_portfolio(presets.STABLE)
    at.run()

    _goal_box(at).set_value("1,000,000").run()
    assert not at.exception
    assert at.session_state["goal_monthly_krw"] == 1_000_000
    body = _body(at)
    assert "시드만" in body and "늘리면" in body


def test_the_screen_calls_it_arithmetic_not_advice(market):
    """'이렇게 하세요' 가 되면 안 됩니다. 분배율이 달라지면 결과도 달라집니다."""
    _market(market)
    at = AppTest.from_file(APP_PATH, default_timeout=90)
    at.session_state["portfolio"] = presets.build_portfolio(presets.STABLE)
    at.run()
    _goal_box(at).set_value("1,000,000").run()
    body = " ".join(m.value for m in at.markdown)
    assert "분배율이 달라지면" in body


def test_goal_survives_switching_slots(market):
    """**이 파일의 핵심.** 목표는 사람의 것이라 전술을 갈아타도 남아야 합니다."""
    _market(market)
    at = AppTest.from_file(APP_PATH, default_timeout=90)
    at.session_state["portfolio"] = presets.build_portfolio(presets.STABLE)
    at.run()
    _goal_box(at).set_value("1,000,000").run()

    [b for b in at.button if b.key == "slot_add"][0].click().run()
    assert not at.exception
    assert at.session_state["slot_active"] == 1            # 다른 전술로 갔는데
    assert at.session_state["goal_monthly_krw"] == 1_000_000   # 목표는 그대로


def test_goal_survives_loading_a_preset(market):
    """예시를 불러오는 건 전술을 바꾸는 것이지 목표를 지우는 게 아닙니다."""
    _market(market)
    at = AppTest.from_file(APP_PATH, default_timeout=90).run()
    _goal_box(at).set_value("500,000").run()

    [b for b in at.button if b.key == "preset_aggressive"][0].click().run()
    assert not at.exception
    assert at.session_state["goal_monthly_krw"] == 500_000


def test_goal_is_saved_outside_the_slots(market):
    """저장 구조에서도 목표가 슬롯 안에 들어가면 안 됩니다."""
    p = Portfolio(name="t", initial_capital_krw=10_000_000)
    p.add(Security(market="US", ticker="SCHD", currency="USD", target_weight=0.3))
    state = slot_service.StoreState(
        slots=[slot_service.slot_from_portfolio(p)], active=0, goal_monthly_krw=700_000)
    text = slot_service.dumps(state)
    assert '"goal":700000' in text.replace(" ", "")
    for slot in slot_service.loads(text).slots:
        assert "goal" not in slot.tactic


def test_a_goal_you_already_passed_is_said_plainly(market):
    _market(market)
    at = AppTest.from_file(APP_PATH, default_timeout=90)
    at.session_state["portfolio"] = presets.build_portfolio(presets.INCOME_100_1E)
    at.run()
    _goal_box(at).set_value("1,000").run()      # 터무니없이 낮은 목표
    assert not at.exception
    body = " ".join(m.value for m in at.markdown)
    assert "목표를 넘었습니다" in body


def test_an_empty_portfolio_with_a_goal_says_it_cannot_tell(market):
    """분배금이 0 이면 비례식의 기준이 없습니다. 아무 숫자나 내놓으면 안 됩니다."""
    _market(market)
    at = AppTest.from_file(APP_PATH, default_timeout=90).run()
    _goal_box(at).set_value("1,000,000").run()
    assert not at.exception
    captions = " ".join(c.value for c in at.caption)
    assert "계산할 수 없습니다" in captions
