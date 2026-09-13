"""수익률의 '분모'가 라벨과 일치하는지 검증.

실제로 있었던 혼동 (TDAQ 사례):
시드 1억 중 450만원만 담았더니, 분배율 15.35% 짜리 종목인데 화면에는
"투자금 대비 예상 수익 0.69%" 로 떴습니다. 라벨은 '투자금 대비'인데 계산은
시드 전체로 나누고 있었기 때문입니다. 백테스트도 같은 이유로 종목이 +21% 인데
+0.97% 로 보였습니다.

- 시드 대비   = 연 분배금 / 내 시드      (현금 놀리는 것까지 반영)
- 투자금 대비 = 연 분배금 / 실제 투자금  (담은 종목들의 평균 분배율)
둘 다 맞는 값이지만, 라벨과 분모가 어긋나면 안 됩니다.
"""

from __future__ import annotations

import pathlib

import pytest
from streamlit.testing.v1 import AppTest

from models.portfolio import Portfolio
from models.security import Security
from services import calculation_service as calc
from services import portfolio_service

APP_PATH = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")


def test_two_yields_use_different_denominators():
    annual = 1_000_000.0
    assert calc.calculate_income_yield(annual, 100_000_000) == pytest.approx(1.0)
    assert calc.calculate_income_yield_on_invested(annual, 10_000_000) == pytest.approx(10.0)


def test_invested_yield_is_zero_when_nothing_invested():
    assert calc.calculate_income_yield_on_invested(500.0, 0.0) == 0.0


def _tdaq_like(market):
    """TDAQ 상황 재현: 1주 25,000원(=25 USD x 1,000), 주당 연 분배금 4 USD (16%)."""
    market.set_fx(rate=1_000.0)
    market.set_us({"HIGH": {"currency": "USD", "latest": 25.0,
                            "distributions": None}})
    p = Portfolio(name="t", initial_capital_krw=100_000_000)
    # 시드의 4.5% 만 담는다
    p.add(Security(market="US", ticker="HIGH", currency="USD", target_weight=0.045,
                   distribution_method="manual", manual_ttm_per_share=4.0))
    return p


def test_seed_yield_is_diluted_by_cash_but_invested_yield_is_not(market):
    p = _tdaq_like(market)
    comp = portfolio_service.compute(p)

    # 담은 종목 자체의 분배율은 4 / 25 = 16%
    assert comp.rows[0].distribution_yield_pct == pytest.approx(16.0)

    # 투자금 대비도 16% 근처여야 한다 (정수주 반올림 때문에 약간 차이)
    assert comp.income_yield_on_invested_pct == pytest.approx(16.0, abs=0.2)

    # 시드 대비는 현금 때문에 훨씬 낮다 (4.5% 만 담았으므로 대략 0.72%)
    assert comp.income_yield_pct == pytest.approx(0.72, abs=0.05)
    assert comp.income_yield_pct < comp.income_yield_on_invested_pct / 10


def test_both_yields_match_when_fully_invested(market):
    market.set_fx(rate=1_000.0)
    market.set_us({"HIGH": {"currency": "USD", "latest": 25.0}})
    p = Portfolio(name="t", initial_capital_krw=10_000_000)
    p.add(Security(market="US", ticker="HIGH", currency="USD", target_weight=1.0,
                   distribution_method="manual", manual_ttm_per_share=4.0))
    comp = portfolio_service.compute(p)

    # 전부 담으면 두 값이 사실상 같아야 한다
    assert comp.income_yield_pct == pytest.approx(comp.income_yield_on_invested_pct, abs=0.1)


def test_screen_shows_the_invested_based_number_for_that_label(market):
    """화면의 '투자금 대비 예상 수익' 은 투자금 기준 값이어야 한다."""
    p = _tdaq_like(market)
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["portfolio"] = p
    at.run()
    assert not at.exception

    comp = portfolio_service.compute(p)
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["투자금 대비 예상 수익"] == f"{comp.income_yield_on_invested_pct:.2f}%"
    assert metrics["시드 대비 예상 수익"] == f"{comp.income_yield_pct:.2f}%"
    # 둘이 눈에 띄게 달라야 이 테스트가 의미 있다
    assert metrics["투자금 대비 예상 수익"] != metrics["시드 대비 예상 수익"]


def test_cash_ratio_is_shown_when_a_lot_of_seed_is_idle(market):
    p = _tdaq_like(market)
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["portfolio"] = p
    at.run()

    metrics = {m.label: m.value for m in at.metric}
    assert "현금 비중" in metrics, "시드가 많이 남으면 현금 비중을 알려줘야 합니다."
    assert metrics["현금 비중"].startswith("95")
