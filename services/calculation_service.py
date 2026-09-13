"""
calculation_service.py  --  순수 계산 함수 모음 (UI 와 분리, 인수인계서 98)
=========================================================================

이 파일의 함수는 모두 "입력 -> 출력" 만 있는 순수 함수입니다.
- Streamlit, 파일 IO, 네트워크에 의존하지 않습니다.
- 여기 있는 공식이 프로그램의 핵심이며, 테스트(tests/test_calculations.py)로 검증됩니다.

금액 단위 규칙
--------------
모든 함수는 "기준 통화(KRW)" 로 환산된 값을 받습니다.
미국 종목의 원화 환산가격(price_krw = price_usd * usdkrw) 은 상위 서비스가 계산해서 넘깁니다.
이렇게 하면 이 파일은 통화를 몰라도 되고, 계산식이 단순해집니다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# 금액 반올림 자리수. 부동소수점 잡음(예: 1e7 * 0.30 = 2999999.9999999995)을 제거합니다.
# 원화는 사실상 소수점이 없지만, USD 환산 중간값을 위해 2자리까지 유지합니다. (인수인계서 119)
MONEY_DECIMALS = 2


def money(x: float) -> float:
    """금액을 MONEY_DECIMALS 자리로 반올림한 값."""
    return round(float(x), MONEY_DECIMALS)


# =====================================================================
# 매수 계산
# =====================================================================
def calculate_target_amount(initial_capital: float, target_weight: float) -> float:
    """목표금액 = 초기자본 x 목표비중.

    target_weight 는 비율(0.30 == 30%). 초기자본/비중이 음수면 오류.
    """
    if initial_capital < 0:
        raise ValueError("초기자본은 0 이상이어야 합니다.")
    if target_weight < 0:
        raise ValueError("목표비중은 0 이상이어야 합니다.")
    return money(initial_capital * target_weight)


def calculate_integer_shares(target_amount: float, price_per_share: float) -> int:
    """정수 매수수량 = floor(목표금액 / 1주 가격).

    목표금액을 "초과하지 않는" 가장 큰 정수 수량입니다. (인수하기서 25, 28)
    가격 정보가 없으면(<= 0) 계산 불가로 보고 ValueError 를 던집니다.
    상위 서비스가 "데이터 없음" 을 먼저 처리해야 합니다.
    """
    if price_per_share <= 0:
        raise ValueError("1주 가격이 없거나 0 이하입니다. 수량을 계산할 수 없습니다.")
    if target_amount <= 0:
        return 0
    return math.floor(target_amount / price_per_share)


def calculate_fractional_shares(target_amount: float, price_per_share: float) -> float:
    """소수점 매수수량 = 목표금액 / 1주 가격 (소수점 매수 ON 일 때만 사용).

    1차 버전 기본값은 정수 매수(OFF)이며, 이 함수는 확장용입니다. (인수인계서 29)
    """
    if price_per_share <= 0:
        raise ValueError("1주 가격이 없거나 0 이하입니다. 수량을 계산할 수 없습니다.")
    if target_amount <= 0:
        return 0.0
    return target_amount / price_per_share


def calculate_actual_investment(shares: float, price_per_share: float) -> float:
    """실제 투자금 = 실제 수량 x 1주 가격."""
    if shares < 0:
        raise ValueError("수량은 0 이상이어야 합니다.")
    if price_per_share < 0:
        raise ValueError("가격은 0 이상이어야 합니다.")
    return money(shares * price_per_share)


def calculate_cash_balance(initial_capital: float, total_actual_investment: float) -> float:
    """잔여 현금 = 초기자본 - 전체 실제 투자금."""
    return money(initial_capital - total_actual_investment)


def calculate_actual_weight(actual_investment: float, initial_capital: float) -> float:
    """실제비중 = 실제 투자금 / 초기자본 (비율). 초기자본 0 이면 0."""
    if initial_capital <= 0:
        return 0.0
    return actual_investment / initial_capital


# =====================================================================
# 목표비중 합계 검증 (인수인계서 23, 101, 102)
# =====================================================================
@dataclass
class WeightCheck:
    total: float          # 합계 비율 (1.10 == 110%)
    is_over: bool         # 100% 초과 여부 (오류)
    cash_weight: float    # 100% 미만이면 현금 비중, 아니면 0.0
    message: str | None   # 사용자 표시 메시지 (오류일 때만)


def check_total_weight(weights: list[float], epsilon: float = 1e-9) -> WeightCheck:
    """목표비중 합계를 검사합니다.

    - 합계 > 100%  : is_over=True, 오류 메시지 포함
    - 합계 <= 100% : 허용. 나머지는 현금 비중으로 반환.
    """
    total = float(sum(weights))
    is_over = total > 1.0 + epsilon
    cash_weight = max(0.0, 1.0 - total) if not is_over else 0.0
    message = None
    if is_over:
        message = f"목표비중 합계가 100%를 초과했습니다. 현재 합계: {total * 100:.2f}%"
    return WeightCheck(total=total, is_over=is_over, cash_weight=cash_weight, message=message)


# =====================================================================
# 분배금 계산 (인수인계서 32~45)
# =====================================================================
def calculate_annual_distribution(shares: float, ttm_per_share: float) -> float:
    """연 예상 분배금 = 보유수량 x (최근 12개월 주당 분배금 합계).

    ttm_per_share 는 "기준 통화(KRW)" 로 환산된 값이어야 합니다.
    미국 ETF 는 상위 서비스가 USD 합계 x 현재 USD/KRW 로 환산해서 넘깁니다. (인수인계서 43)
    """
    if shares < 0:
        raise ValueError("수량은 0 이상이어야 합니다.")
    if ttm_per_share < 0:
        raise ValueError("주당 분배금은 0 이상이어야 합니다.")
    return shares * ttm_per_share


def calculate_monthly_distribution(shares: float, ttm_per_share: float) -> float:
    """월 예상 분배금 = 연 예상 분배금 / 12.

    커버드콜 ETF 도 "이번 달 분배금 x 12" 가 아니라
    최근 12개월 실제 합계 / 12 로 계산합니다. (인수인계서 45)
    """
    return calculate_annual_distribution(shares, ttm_per_share) / 12.0


def calculate_income_yield(annual_distribution: float, initial_capital: float) -> float:
    """시드 대비 현금수익률(%) = 연 예상 분배금 / 내 시드 x 100. (인수인계서 42)

    현금으로 남겨둔 몫까지 분모에 포함합니다. "내 전체 자산이 실제로 얼마를
    만들어내는가" 를 보는 값이라, 시드의 일부만 담으면 낮게 나오는 것이 정상입니다.
    """
    if initial_capital <= 0:
        return 0.0
    return annual_distribution / initial_capital * 100.0


def calculate_income_yield_on_invested(annual_distribution: float,
                                       actual_investment: float) -> float:
    """투자금 대비 현금수익률(%) = 연 예상 분배금 / 실제 투자금 x 100.

    시드가 아니라 "실제로 종목에 들어간 돈" 이 분모입니다. 담은 종목들의 평균
    분배율에 해당하며, 현금을 얼마나 남겨뒀는지와 무관합니다.

    왜 두 개가 따로 필요한가
    ------------------------
    시드 1억 중 450만원만 담으면 두 값이 크게 벌어집니다(예: 시드 대비 0.69% /
    투자금 대비 15.35%). 하나만 보여주면서 라벨을 반대로 붙이면 "분배율 15% 짜리를
    담았는데 왜 0.69% 라고 나오지?" 하는 오해가 생깁니다. (실제로 있었던 혼동)
    """
    if actual_investment <= 0:
        return 0.0
    return annual_distribution / actual_investment * 100.0


def calculate_distribution_yield(ttm_per_share: float | None,
                                 price_per_share: float | None) -> float | None:
    """종목 단위 분배율(%) = 최근 12개월 주당 분배금 / 현재가 x 100.

    "이 종목이 지금 가격 대비 연간 몇 % 를 분배하는가" 를 보여주는 참고 지표입니다.
    (은행 예적금 금리처럼 '추천'이 아니라 그대로 계산된 비율일 뿐입니다 -- 인수인계서 6, 106)
    가격/TTM 둘 다 같은 통화(그 종목의 원래 통화)를 쓰므로 환율 변환이 필요 없습니다.
    가격이 없거나 0 이하, 또는 TTM 값이 없으면(데이터 없음) None.
    """
    if price_per_share is None or price_per_share <= 0 or ttm_per_share is None:
        return None
    return (ttm_per_share / price_per_share) * 100.0


# =====================================================================
# USD -> KRW 환산 헬퍼 (환율은 fx_service 가 조회, 여기서는 곱셈만)
# =====================================================================
def to_krw(amount_usd: float, usdkrw: float) -> float:
    """USD 금액을 원화로 환산. 환율이 없으면(<= 0) 오류. (인수인계서 52, 117)"""
    if usdkrw is None or usdkrw <= 0:
        raise ValueError("USD/KRW 환율 데이터가 없어 원화로 환산할 수 없습니다.")
    return amount_usd * usdkrw
