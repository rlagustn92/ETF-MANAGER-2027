"""
services/portfolio_service.py  --  포트폴리오 전체 계산 오케스트레이션
====================================================================

"매수수량 계산 로직을 바꿔줘" -> 이 파일 + services/calculation_service.py

흐름 (인수인계서 28):
    1. 목표금액 = 초기자본 x 목표비중
    2. 가격 조회 (미국: 현재가 x 현재환율 -> 원화)
    3. 정수 수량 = floor(목표금액 / 원화가격)
    4. 실제 투자금 = 수량 x 원화가격
    5. 잔여현금 = 초기자본 - 실제투자금 합계
    6. 실제비중 = 실제투자금 / 초기자본
    7. 분배금 = 수량 x 최근12개월 주당분배금(원화)  -> /12 = 월 예상

한 종목의 데이터 오류가 전체를 죽이지 않도록 종목별 warnings 로 담습니다. (인수인계서 104)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

import config
from data.providers.base import DataUnavailable
from data.providers.registry import get_provider
from models.portfolio import Portfolio
from models.security import MARKET_US, Security
from services import calculation_service as calc
from services import fx_service
from services.distribution_service import DistributionResult, compute_ttm


@dataclass
class RowResult:
    security: Security
    currency: str
    price_native: float | None = None
    price_krw: float | None = None
    price_source: str = ""
    price_as_of: date | None = None
    target_amount_krw: float = 0.0
    shares: float = 0.0
    actual_investment_krw: float = 0.0
    target_weight: float = 0.0
    actual_weight: float = 0.0
    ttm_per_share_native: float | None = None
    ttm_per_share_krw: float | None = None
    distribution_yield_pct: float | None = None   # 현재가 대비 최근 12개월 분배금 비율(%)
    distribution_window_start: date | None = None
    distribution_window_end: date | None = None
    distribution_n_payments: int = 0
    distribution_payments: list[tuple[date, float]] = field(default_factory=list)
    # 상장 12개월 미만 종목의 연환산 추정 관련 (사용자 요청) -- distribution_service 참고
    distribution_is_estimated: bool = False
    distribution_months_since_listing: float | None = None
    distribution_actual_total_native: float | None = None
    monthly_distribution_krw: float = 0.0
    annual_distribution_krw: float = 0.0
    distribution_included: bool = True
    distribution_note: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class PortfolioComputation:
    rows: list[RowResult]
    initial_capital_krw: float
    total_actual_investment_krw: float
    cash_balance_krw: float
    monthly_distribution_krw: float
    annual_distribution_krw: float
    income_yield_pct: float                 # 시드 대비 (현금 포함)
    income_yield_on_invested_pct: float      # 투자금 대비 (실제 담은 돈 기준)
    weight_total: float
    weight_is_over: bool
    weight_message: str | None
    cash_weight: float
    usdkrw: float | None
    usdkrw_as_of: date | None
    usdkrw_message: str
    data_as_of: date | None
    last_updated: datetime
    warnings: list[str] = field(default_factory=list)


def resolve_price(sec: Security) -> tuple[float | None, str, date | None, str | None]:
    """(native_price, source, as_of, warning) 반환. 실패 시 native_price=None.

    공개 함수입니다 -- app.py 가 compute() 실행 "전"에 선택 종목의 현재가를 미리 조회해서
    (수량으로 목표비중 설정) 같은 편집 UI 에 즉시 반영할 때도 이 함수를 재사용합니다.
    캐시(data/providers/cache.py)를 거치므로 두 번 불러도 두 번째는 저렴합니다.
    """
    if sec.manual_price is not None and float(sec.manual_price) > 0:
        return float(sec.manual_price), "manual", date.today(), None
    try:
        q = get_provider(sec.market).get_latest_price(sec.ticker)
        return q.price, q.source, q.as_of, None
    except (DataUnavailable, ValueError) as e:
        return None, "", None, f"[{sec.ticker}] 가격 데이터 없음: {e}"
    except Exception as e:  # provider 내부 오류도 앱을 죽이지 않음
        return None, "", None, f"[{sec.ticker}] 가격 조회 중 오류: {e}"


def compute(portfolio: Portfolio) -> PortfolioComputation:
    capital = float(portfolio.initial_capital_krw)
    fractional = bool(portfolio.fractional_shares)

    fx = fx_service.current_usdkrw()
    usdkrw = fx.rate if fx.ok else None
    usdkrw_msg = "" if fx.ok else fx.message

    rows: list[RowResult] = []
    warnings: list[str] = []
    price_dates: list[date] = []

    for sec in portfolio.securities:
        row = RowResult(security=sec, currency=sec.currency,
                        target_weight=float(sec.target_weight),
                        distribution_included=bool(sec.distribution_enabled))

        native, source, as_of, warn = resolve_price(sec)
        row.price_native = native
        row.price_source = source
        row.price_as_of = as_of
        if warn:
            row.warnings.append(warn)
        if as_of:
            price_dates.append(as_of)

        # --- 원화 환산 가격 ---
        price_krw: float | None = None
        if native is not None:
            if sec.market == MARKET_US and sec.currency == "USD":
                if usdkrw is None:
                    row.warnings.append(
                        "USD/KRW 환율 데이터가 없어 원화 환산을 할 수 없습니다."
                    )
                else:
                    price_krw = calc.to_krw(native, usdkrw)
            else:
                price_krw = native  # KRW 종목
        row.price_krw = price_krw

        # --- 목표금액 / 수량 / 실제투자금 / 실제비중 ---
        row.target_amount_krw = calc.calculate_target_amount(capital, row.target_weight)
        if price_krw is not None and price_krw > 0:
            if fractional:
                row.shares = calc.calculate_fractional_shares(row.target_amount_krw, price_krw)
            else:
                row.shares = calc.calculate_integer_shares(row.target_amount_krw, price_krw)
            row.actual_investment_krw = calc.calculate_actual_investment(row.shares, price_krw)
        else:
            row.shares = 0.0
            row.actual_investment_krw = 0.0
        row.actual_weight = calc.calculate_actual_weight(row.actual_investment_krw, capital)
        # Security.actual_shares 는 "계산 결과 캐시" 필드입니다(모델 docstring 참고).
        # 다음 렌더에서 '수량으로 설정' 입력의 기본값으로 재사용합니다.
        sec.actual_shares = row.shares

        # --- 분배금 ---
        dist: DistributionResult = compute_ttm(sec)
        row.distribution_note = dist.note
        row.ttm_per_share_native = dist.ttm_per_share_native
        row.distribution_window_start = dist.window_start
        row.distribution_window_end = dist.window_end
        row.distribution_n_payments = dist.n_payments_ttm
        row.distribution_payments = dist.payments
        row.distribution_is_estimated = dist.is_estimated_annualized
        row.distribution_months_since_listing = dist.months_since_listing
        row.distribution_actual_total_native = dist.actual_payment_total_native
        if dist.is_estimated_annualized:
            row.warnings.append(
                f"[{sec.ticker}] 분배금은 상장 후 약 {dist.months_since_listing:.1f}개월 "
                f"실적을 연환산한 추정치입니다."
            )
        # 분배율(TTM) = 현재가 대비 최근 12개월 분배금 비율. '분배금 계산 포함' 토글과 무관하게
        # 종목 자체의 참고 지표로 항상 계산합니다 (가격/TTM 데이터가 있을 때만).
        row.distribution_yield_pct = calc.calculate_distribution_yield(
            dist.ttm_per_share_native, native)
        if row.distribution_included and dist.has_data:
            ttm_native = float(dist.ttm_per_share_native)
            if sec.currency == "USD":
                if usdkrw is None:
                    row.warnings.append("환율이 없어 분배금을 원화로 환산하지 못했습니다.")
                    ttm_krw = None
                else:
                    ttm_krw = ttm_native * usdkrw
            else:
                ttm_krw = ttm_native
            row.ttm_per_share_krw = ttm_krw
            if ttm_krw is not None:
                row.annual_distribution_krw = calc.calculate_annual_distribution(
                    row.shares, ttm_krw)
                row.monthly_distribution_krw = calc.calculate_monthly_distribution(
                    row.shares, ttm_krw)
        elif row.distribution_included and not dist.has_data:
            row.warnings.append(f"[{sec.ticker}] 분배금 {config.NO_DATA_TEXT}")

        rows.append(row)

    # --- 합계 ---
    total_invest = sum(r.actual_investment_krw for r in rows)
    cash = calc.calculate_cash_balance(capital, total_invest)
    monthly = sum(r.monthly_distribution_krw for r in rows)
    annual = sum(r.annual_distribution_krw for r in rows)
    income_yield = calc.calculate_income_yield(annual, capital)
    income_yield_invested = calc.calculate_income_yield_on_invested(annual, total_invest)

    wc = calc.check_total_weight([r.target_weight for r in rows], config.WEIGHT_SUM_EPSILON)

    for r in rows:
        warnings.extend(r.warnings)
    if usdkrw_msg:
        warnings.append(usdkrw_msg)

    return PortfolioComputation(
        rows=rows,
        initial_capital_krw=capital,
        total_actual_investment_krw=total_invest,
        cash_balance_krw=cash,
        monthly_distribution_krw=monthly,
        annual_distribution_krw=annual,
        income_yield_pct=income_yield,
        income_yield_on_invested_pct=income_yield_invested,
        weight_total=wc.total,
        weight_is_over=wc.is_over,
        weight_message=wc.message,
        cash_weight=wc.cash_weight,
        usdkrw=usdkrw,
        usdkrw_as_of=fx.as_of,
        usdkrw_message=usdkrw_msg,
        data_as_of=max(price_dates) if price_dates else None,
        last_updated=config.now_local(),   # 화면에 KST 로 표시되므로 한국 시간 기준
        warnings=warnings,
    )
