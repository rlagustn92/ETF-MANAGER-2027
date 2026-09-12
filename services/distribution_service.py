"""
services/distribution_service.py  --  분배금(배당) 계산 (인수인계서 32~45)
======================================================================

"월 예상 분배금 계산 방식을 바꿔줘" 같은 요청이 오면 이 파일만 고치면 됩니다. (인수인계서 107-4)

기본 방식: 최근 12개월 실제 분배금 합계(TTM) 를 주당 기준으로 구한 뒤
    연 예상 = 보유수량 x TTM(주당)
    월 예상 = 연 예상 / 12

데이터가 없으면 추정하지 않고 ttm_per_share_native=None 으로 표시합니다. (인수인계서 38, 44)

예외: 상장/데이터 시작일이 최근 12개월 이내인 "젊은" 종목 (사용자 요청으로 추가)
---------------------------------------------------------------------------
이 종목들은 애초에 만 12개월치 데이터가 존재할 수 없으므로, 실제 지급 횟수가
2회 이상이면 "실제 관측 기간 -> 365일" 비율로 연환산한 추정치를 계산합니다.
- 이 값은 반드시 "추정치"로 명확히 표시되며 (is_estimated_annualized=True),
  실제 지급 횟수·관측 기간을 note 에 그대로 남겨 근거를 확인할 수 있게 합니다.
- 실제 지급이 0~1회뿐이면 연환산하지 않습니다(근거가 너무 부족). 대신 상장일 기준
  안내만 남깁니다.
- 상장/데이터 시작일을 확인할 수 없으면(provider 가 모르면) 이 예외 로직 자체를
  적용하지 않고 기존 방식(있는 그대로 합산)으로 처리합니다 -- 확인 안 되는 걸
  "젊은 종목"이라고 임의로 단정하지 않습니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

import config
from data.providers.base import DataUnavailable
from data.providers.registry import get_provider
from models.security import DIST_METHOD_MANUAL, Security

DAYS_PER_YEAR = 365.0
DAYS_PER_MONTH = 30.44
MIN_PAYMENTS_TO_ANNUALIZE = 2   # 이보다 적으면(0~1회) 연환산하지 않음


@dataclass
class DistributionResult:
    ticker: str
    currency: str
    method: str                          # "auto_ttm" | "manual"
    ttm_per_share_native: float | None   # None => 데이터 없음 (계산 불가)
    n_payments_ttm: int
    window_start: date | None
    window_end: date | None
    source: str
    note: str = ""
    # 자동(TTM) 방식일 때, 합계에 실제로 들어간 개별 지급 내역 (지급일, 주당 금액).
    # "이 숫자가 어떤 근거로 나왔는지" 를 사용자가 직접 확인할 수 있도록 함.
    payments: list[tuple[date, float]] = field(default_factory=list)
    # 상장 12개월 미만 종목의 연환산 추정 관련 (모두 해당 없으면 기본값 유지)
    is_estimated_annualized: bool = False   # True 면 ttm_per_share_native 가 "연환산 추정치"
    months_since_listing: float | None = None
    actual_payment_total_native: float | None = None   # 연환산 전, 실제 관측된 지급 합계

    @property
    def has_data(self) -> bool:
        return self.ttm_per_share_native is not None


def _ttm_window(as_of: date | None = None) -> tuple[date, date]:
    end = as_of or date.today()
    start = end - timedelta(days=365)  # 최근 12개월
    return start, end


def compute_ttm(sec: Security, as_of: date | None = None) -> DistributionResult:
    """한 종목의 최근 12개월 주당 분배금 합계를 구합니다 (해당 종목 통화 기준)."""
    start, end = _ttm_window(as_of)

    # 1) 직접 입력 방식
    if sec.distribution_method == DIST_METHOD_MANUAL:
        val = sec.manual_ttm_per_share
        if val is None or float(val) < 0:
            return DistributionResult(
                ticker=sec.ticker, currency=sec.currency, method="manual",
                ttm_per_share_native=None, n_payments_ttm=0,
                window_start=start, window_end=end, source="manual",
                note="직접 입력값이 없습니다.",
            )
        return DistributionResult(
            ticker=sec.ticker, currency=sec.currency, method="manual",
            ttm_per_share_native=float(val), n_payments_ttm=0,
            window_start=start, window_end=end, source="manual",
            note="사용자가 입력한 최근 12개월 주당 분배금.",
        )

    # 2) 자동(TTM) 방식
    provider = get_provider(sec.market)
    try:
        series: pd.Series = provider.get_distributions(sec.ticker, start, end)
    except DataUnavailable as e:
        return DistributionResult(
            ticker=sec.ticker, currency=sec.currency, method="auto_ttm",
            ttm_per_share_native=None, n_payments_ttm=0,
            window_start=start, window_end=end, source=provider.name,
            note=str(e),
        )

    # 상장/데이터 시작일 확인 -- 최근 12개월 이내에 상장된 "젊은" 종목인지 판단.
    # 확인이 안 되면(None) 아래 젊은 종목 예외 로직을 아예 타지 않습니다(추측 금지).
    listing_first = provider.get_listing_first_date(sec.ticker)
    is_young = listing_first is not None and listing_first > start
    actual_days = (end - listing_first).days if is_young else None
    months = (actual_days / DAYS_PER_MONTH) if actual_days else None

    if series is None or len(series) == 0:
        if is_young:
            return DistributionResult(
                ticker=sec.ticker, currency=sec.currency, method="auto_ttm",
                ttm_per_share_native=0.0, n_payments_ttm=0,
                window_start=start, window_end=end, source=provider.name,
                note=(f"⚠ 상장(데이터 시작) 후 약 {months:.1f}개월밖에 되지 않았고, "
                     f"그동안 분배금 지급 이력이 없습니다. 12개월이 지나야 정확한 "
                     f"분배금을 계산할 수 있습니다."),
                months_since_listing=months,
            )
        # 소스는 있으나 최근 12개월 지급 이력이 없음 -> 실제 0 으로 간주 (인수인계서 36)
        return DistributionResult(
            ticker=sec.ticker, currency=sec.currency, method="auto_ttm",
            ttm_per_share_native=0.0, n_payments_ttm=0,
            window_start=start, window_end=end, source=provider.name,
            note="최근 12개월 분배금 지급 이력이 없습니다.",
        )

    total = float(series.sum())
    n = int(len(series))
    payments = sorted(
        ((ts.date() if hasattr(ts, "date") else ts, float(v)) for ts, v in series.items()),
        key=lambda p: p[0], reverse=True,   # 최근 지급일이 먼저 보이도록
    )

    if is_young and actual_days and actual_days > 0:
        if n >= MIN_PAYMENTS_TO_ANNUALIZE:
            annualized = total * (DAYS_PER_YEAR / actual_days)
            note = (
                f"⚠ 추정치: 상장(데이터 시작) 후 약 {months:.1f}개월, 아직 만 12개월이 "
                f"되지 않았습니다. 실제 지급 {n}회 합계 {total:,.4f} {sec.currency}"
                f"(관측 기간 {actual_days}일)를 365일 기준으로 연환산한 값입니다. "
                f"실제 향후 분배금과 다를 수 있습니다."
            )
            return DistributionResult(
                ticker=sec.ticker, currency=sec.currency, method="auto_ttm",
                ttm_per_share_native=annualized, n_payments_ttm=n,
                window_start=start, window_end=end, source=provider.name,
                note=note, payments=payments,
                is_estimated_annualized=True, months_since_listing=months,
                actual_payment_total_native=total,
            )
        # 지급 이력이 0~1회뿐 -> 연환산 근거 부족, 연환산하지 않음
        note = (
            f"⚠ 상장(데이터 시작) 후 약 {months:.1f}개월, 실제 지급 이력이 {n}회뿐이라 "
            f"연환산하지 않았습니다(최소 {MIN_PAYMENTS_TO_ANNUALIZE}회 필요). "
            f"12개월이 지나야 정확한 분배금을 계산할 수 있습니다."
        )
        return DistributionResult(
            ticker=sec.ticker, currency=sec.currency, method="auto_ttm",
            ttm_per_share_native=total, n_payments_ttm=n,
            window_start=start, window_end=end, source=provider.name,
            note=note, payments=payments, months_since_listing=months,
        )

    # 정상 케이스: 상장 12개월 이상 지났거나(또는 상장일 확인 불가) -- 기존과 동일
    return DistributionResult(
        ticker=sec.ticker, currency=sec.currency, method="auto_ttm",
        ttm_per_share_native=total, n_payments_ttm=n,
        window_start=start, window_end=end, source=provider.name,
        note=config.DISTRIBUTION_DISCLAIMER, payments=payments,
    )
