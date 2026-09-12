"""portfolio_service 통합 계산 테스트 (네트워크 없음). 인수인계서 24~44, 115."""

import pytest

from models.portfolio import Portfolio
from models.security import DIST_METHOD_MANUAL, Security
from services import portfolio_service

from tests.conftest import series


def _p(cap=10_000_000, **kw):
    return Portfolio(name="t", initial_capital_krw=cap, **kw)


def test_integer_shares_and_cash_krw_stock(market):
    market.set_kr({"005930": {"currency": "KRW", "latest": 70_000}})
    p = _p(10_000_000)
    p.add(Security(market="KR", ticker="005930", currency="KRW", target_weight=0.30,
                   distribution_enabled=False))
    comp = portfolio_service.compute(p)
    row = comp.rows[0]
    assert row.target_amount_krw == 3_000_000
    assert row.shares == 42
    assert row.actual_investment_krw == 2_940_000
    assert comp.total_actual_investment_krw == 2_940_000
    assert comp.cash_balance_krw == 7_060_000
    assert row.actual_weight == pytest.approx(0.294)


def test_us_stock_uses_current_fx(market):
    market.set_fx(rate=1_400)
    market.set_us({"QQQ": {"currency": "USD", "latest": 500.0}})
    p = _p(10_000_000)
    p.add(Security(market="US", ticker="QQQ", currency="USD", target_weight=0.30,
                   distribution_enabled=False))
    comp = portfolio_service.compute(p)
    row = comp.rows[0]
    assert row.price_krw == 700_000            # 500 x 1400
    assert row.shares == 4                     # floor(3,000,000 / 700,000)
    assert row.actual_investment_krw == 2_800_000


def test_weight_over_100_flagged(market):
    market.set_kr({"A": {"currency": "KRW", "latest": 100}, "B": {"currency": "KRW", "latest": 100}})
    p = _p()
    p.add(Security(market="KR", ticker="A", currency="KRW", target_weight=0.60))
    p.add(Security(market="KR", ticker="B", currency="KRW", target_weight=0.50))
    comp = portfolio_service.compute(p)
    assert comp.weight_is_over is True
    assert "110" in comp.weight_message


def test_weight_under_100_is_cash(market):
    market.set_kr({"A": {"currency": "KRW", "latest": 100}, "B": {"currency": "KRW", "latest": 100}})
    p = _p()
    p.add(Security(market="KR", ticker="A", currency="KRW", target_weight=0.50))
    p.add(Security(market="KR", ticker="B", currency="KRW", target_weight=0.30))
    comp = portfolio_service.compute(p)
    assert comp.weight_is_over is False
    assert comp.cash_weight == pytest.approx(0.20)


def test_missing_price_does_not_crash_other_rows(market):
    market.set_kr({"GOOD": {"currency": "KRW", "latest": 1_000},
                   "BAD": {"currency": "KRW", "latest": "error"}})
    p = _p(1_000_000)
    p.add(Security(market="KR", ticker="GOOD", currency="KRW", target_weight=0.50))
    p.add(Security(market="KR", ticker="BAD", currency="KRW", target_weight=0.50))
    comp = portfolio_service.compute(p)
    good = next(r for r in comp.rows if r.security.ticker == "GOOD")
    bad = next(r for r in comp.rows if r.security.ticker == "BAD")
    assert good.shares == 500
    assert bad.shares == 0
    assert bad.price_krw is None
    assert any("가격 데이터 없음" in w for w in comp.warnings)


def test_fx_missing_blocks_us_conversion_only(market):
    market.set_fx(ok=False)
    market.set_us({"QQQ": {"currency": "USD", "latest": 500.0}})
    market.set_kr({"005930": {"currency": "KRW", "latest": 70_000}})
    p = _p(10_000_000)
    p.add(Security(market="US", ticker="QQQ", currency="USD", target_weight=0.30))
    p.add(Security(market="KR", ticker="005930", currency="KRW", target_weight=0.30,
                   distribution_enabled=False))
    comp = portfolio_service.compute(p)
    us_row = next(r for r in comp.rows if r.security.ticker == "QQQ")
    kr_row = next(r for r in comp.rows if r.security.ticker == "005930")
    assert us_row.price_krw is None and us_row.shares == 0
    assert kr_row.shares == 42       # 한국 종목은 정상 계산
    assert any("환율" in w for w in comp.warnings)


def test_distribution_ttm_auto_and_monthly(market):
    # 최근 12개월 주당 분배금 합계 $7.20, 보유수량 x 그 값 / 12 = 월 예상
    # 모두 "오늘 기준 최근 12개월" 안에 있어야 함 (미래 지급일은 제외됨)
    divs = series([("2025-12-15", 1.80), ("2026-03-15", 1.80),
                   ("2026-06-15", 1.80), ("2026-09-01", 1.80)])
    market.set_fx(rate=1_000)
    market.set_us({"JEPX": {"currency": "USD", "latest": 100.0, "distributions": divs}})
    p = _p(10_000_000)
    p.add(Security(market="US", ticker="JEPX", currency="USD", target_weight=1.0))
    comp = portfolio_service.compute(p)
    row = comp.rows[0]
    # 가격 100 x 1000 = 100,000 KRW, 목표금액 10,000,000 -> 100주
    assert row.shares == 100
    # ttm per share = 7.20 USD -> x1000 = 7200 KRW ; 연 = 100 * 7200 = 720,000 ; 월 = 60,000
    assert row.annual_distribution_krw == pytest.approx(720_000)
    assert row.monthly_distribution_krw == pytest.approx(60_000)
    assert comp.income_yield_pct == pytest.approx(7.2)

    # 분배율(TTM) = 주당 분배금 합계(현지통화) / 현재가(현지통화) * 100 = 7.20 / 100 * 100 = 7.2%
    assert row.distribution_yield_pct == pytest.approx(7.2)
    # "어떻게 계산됐는지" 확인할 수 있도록 개별 지급 내역과 기간도 함께 담겨야 함
    assert row.distribution_n_payments == 4
    assert len(row.distribution_payments) == 4
    assert sum(amt for _, amt in row.distribution_payments) == pytest.approx(7.20)
    assert row.distribution_window_start is not None and row.distribution_window_end is not None


def test_distribution_yield_computed_even_when_toggle_off(market):
    # 분배율은 종목 자체의 참고 지표이므로 '분배금 계산 포함' 토글과 무관하게 항상 계산되어야 함
    divs = series([("2026-03-15", 2.0), ("2026-06-15", 2.0), ("2026-09-01", 2.0)])
    market.set_fx(rate=1_000)
    market.set_us({"X": {"currency": "USD", "latest": 100.0, "distributions": divs}})
    p = _p(10_000_000)
    p.add(Security(market="US", ticker="X", currency="USD", target_weight=1.0,
                   distribution_enabled=False))
    comp = portfolio_service.compute(p)
    row = comp.rows[0]
    assert comp.monthly_distribution_krw == 0.0             # 포트폴리오 합계에서는 제외
    assert row.distribution_yield_pct == pytest.approx(6.0)  # 하지만 종목 지표는 그대로 나옴


def test_distribution_yield_none_when_price_missing(market):
    divs = series([("2026-03-15", 2.0)])
    market.set_us({"X": {"currency": "USD", "latest": "error", "distributions": divs}})
    p = _p(10_000_000)
    p.add(Security(market="US", ticker="X", currency="USD", target_weight=1.0))
    comp = portfolio_service.compute(p)
    assert comp.rows[0].distribution_yield_pct is None


def test_distribution_no_data_is_not_guessed(market):
    market.set_kr({"005930": {"currency": "KRW", "latest": 50_000, "distributions": "error"}})
    p = _p(10_000_000)
    p.add(Security(market="KR", ticker="005930", currency="KRW", target_weight=1.0))
    comp = portfolio_service.compute(p)
    row = comp.rows[0]
    assert row.monthly_distribution_krw == 0.0
    assert row.ttm_per_share_native is None
    assert any("분배금" in w for w in comp.warnings)


def test_distribution_manual_input(market):
    market.set_kr({"005930": {"currency": "KRW", "latest": 50_000}})
    p = _p(10_000_000)
    p.add(Security(market="KR", ticker="005930", currency="KRW", target_weight=1.0,
                   distribution_method=DIST_METHOD_MANUAL, manual_ttm_per_share=1_500))
    comp = portfolio_service.compute(p)
    row = comp.rows[0]
    assert row.shares == 200          # 10,000,000 / 50,000
    assert row.annual_distribution_krw == pytest.approx(200 * 1_500)


def test_distribution_excluded_when_toggle_off(market):
    divs = series([("2026-03-15", 2.0), ("2026-06-15", 2.0), ("2026-09-15", 2.0)])
    market.set_fx(rate=1_000)
    market.set_us({"X": {"currency": "USD", "latest": 100.0, "distributions": divs}})
    p = _p(10_000_000)
    p.add(Security(market="US", ticker="X", currency="USD", target_weight=1.0,
                   distribution_enabled=False))
    comp = portfolio_service.compute(p)
    assert comp.monthly_distribution_krw == 0.0
