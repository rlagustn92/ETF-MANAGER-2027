"""핵심 계산 함수 테스트 (인수인계서 99~102, 115)."""

import math

import pytest

from services import calculation_service as calc


# --- 인수인계서 99: 정수주 계산 -------------------------------------------------
def test_integer_shares_example_from_spec():
    initial = 10_000_000
    weight = 0.30
    price = 70_000

    target = calc.calculate_target_amount(initial, weight)
    assert target == 3_000_000

    shares = calc.calculate_integer_shares(target, price)
    assert shares == 42  # floor(3,000,000 / 70,000) = floor(42.857) = 42

    invest = calc.calculate_actual_investment(shares, price)
    assert invest == 2_940_000

    # 인수인계서 99 의 "잔여금 60,000" = 이 종목의 목표금액 대비 미사용액
    assert target - invest == 60_000

    # 포트폴리오 잔여현금 = 초기자본 - 전체 실제투자금 (이 종목만 있다고 가정)
    assert calc.calculate_cash_balance(initial, invest) == 7_060_000

    assert calc.calculate_actual_weight(invest, initial) == pytest.approx(0.294)


def test_integer_shares_never_exceeds_target():
    # 목표금액을 초과하지 않는 가장 큰 정수 (인수인계서 25, 28)
    assert calc.calculate_integer_shares(2_999_999, 70_000) == 42
    assert calc.calculate_integer_shares(2_940_000, 70_000) == 42
    assert calc.calculate_integer_shares(2_939_999, 70_000) == 41


def test_integer_shares_zero_when_target_too_small():
    assert calc.calculate_integer_shares(50_000, 70_000) == 0


def test_price_missing_raises():
    with pytest.raises(ValueError):
        calc.calculate_integer_shares(1_000_000, 0)
    with pytest.raises(ValueError):
        calc.calculate_integer_shares(1_000_000, -5)


# --- 인수인계서 100: 환율 환산 -----------------------------------------------
def test_fx_conversion_example_from_spec():
    initial = 10_000_000
    weight = 0.30
    usdkrw = 1_400
    price_usd = 500

    price_krw = calc.to_krw(price_usd, usdkrw)
    assert price_krw == 700_000

    target = calc.calculate_target_amount(initial, weight)
    assert target == 3_000_000

    shares = calc.calculate_integer_shares(target, price_krw)
    assert shares == 4  # floor(3,000,000 / 700,000) = 4

    invest = calc.calculate_actual_investment(shares, price_krw)
    assert invest == 2_800_000


def test_to_krw_missing_rate_raises():
    with pytest.raises(ValueError):
        calc.to_krw(500, 0)
    with pytest.raises(ValueError):
        calc.to_krw(500, None)  # type: ignore[arg-type]


# --- 인수인계서 101/102: 목표비중 합계 -------------------------------------------
def test_weight_sum_over_100_is_error():
    wc = calc.check_total_weight([0.60, 0.50])  # 110%
    assert wc.is_over is True
    assert "110" in wc.message
    assert wc.cash_weight == 0.0


def test_weight_sum_under_100_is_ok_with_cash():
    wc = calc.check_total_weight([0.50, 0.30])  # 80%
    assert wc.is_over is False
    assert wc.message is None
    assert wc.cash_weight == pytest.approx(0.20)


def test_weight_sum_exactly_100_ok():
    wc = calc.check_total_weight([0.30, 0.20, 0.20, 0.15, 0.10, 0.05])
    assert wc.is_over is False
    assert wc.cash_weight == pytest.approx(0.0)


# --- 분배금 (인수인계서 34, 40, 41, 42) ----------------------------------------
def test_distribution_monthly_annual_yield():
    shares = 100
    ttm_per_share = 7.20  # 최근 12개월 주당 분배금 합계

    annual = calc.calculate_annual_distribution(shares, ttm_per_share)
    assert annual == pytest.approx(720.0)

    monthly = calc.calculate_monthly_distribution(shares, ttm_per_share)
    assert monthly == pytest.approx(60.0)

    # 예상 현금수익률 = 연 분배금 / 초기자본 * 100
    assert calc.calculate_income_yield(720.0, 10_000) == pytest.approx(7.2)


def test_income_yield_zero_capital():
    assert calc.calculate_income_yield(1000, 0) == 0.0


# --- 종목 단위 분배율(TTM), 사용자 요청으로 추가된 지표 -------------------------
def test_distribution_yield_basic():
    # 최근 12개월 분배금 합계 $3.00, 현재가 $60 -> 분배율 5%
    assert calc.calculate_distribution_yield(3.0, 60.0) == pytest.approx(5.0)


def test_distribution_yield_none_when_price_missing():
    assert calc.calculate_distribution_yield(3.0, None) is None
    assert calc.calculate_distribution_yield(3.0, 0) is None
    assert calc.calculate_distribution_yield(3.0, -1) is None


def test_distribution_yield_none_when_ttm_missing():
    assert calc.calculate_distribution_yield(None, 60.0) is None


def test_distribution_yield_zero_ttm_is_zero_percent_not_none():
    # 분배 이력이 실제로 없는 종목(0.0)과 "데이터 없음"(None)은 구분되어야 함
    assert calc.calculate_distribution_yield(0.0, 60.0) == pytest.approx(0.0)


# --- '수량으로 설정' 기능 정밀도 (사용자 요청): 수량 -> 목표비중 역산 후
#     다시 floor(목표금액/가격) 을 해도 원래 입력한 수량이 정확히 나와야 함 -----------
def test_quantity_to_weight_roundtrip_needs_high_precision():
    # 실제 브라우저 테스트에서 나온 값: QQQ 가격 708.69 USD, 환율 1345.68, 수량 20주
    price_native, fx, qty, capital = 708.69, 1345.68, 20, 100_000_000
    price_krw = price_native * fx

    # 슬라이더 표시용으로 소수점 2자리까지만 반올림하면(이번 요청 전 구현) 19주로 깎여버림
    weight_2dp = round((qty * price_krw) / capital * 100.0, 2) / 100.0
    target_2dp = calc.calculate_target_amount(capital, weight_2dp)
    assert calc.calculate_integer_shares(target_2dp, price_krw) == 19   # 회귀 방지용 재현

    # '수량으로 설정' 은 (수량×가격 + 0.5원) 을 목표비중으로 역산해야, 목표금액 계산의
    # 원 단위 반올림이 내림 방향으로 떨어지는 경계에서도 입력한 수량이 정확히 재현됨
    weight_padded = (qty * price_krw + 0.5) / capital * 100.0
    target_padded = calc.calculate_target_amount(capital, weight_padded / 100.0)
    assert calc.calculate_integer_shares(target_padded, price_krw) == qty


# --- 소수점 매수 (확장 기능, 인수인계서 29) ------------------------------------
def test_fractional_shares():
    assert calc.calculate_fractional_shares(3_000_000, 700_000) == pytest.approx(4.285714, rel=1e-4)
