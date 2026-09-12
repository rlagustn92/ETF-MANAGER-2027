"""distribution_service.compute_ttm 테스트 -- 특히 상장 12개월 미만 종목의
연환산 추정 기능 (사용자 요청, 네트워크 없음).

규칙 (사용자와 합의한 내용):
    - 상장(데이터 시작) 후 12개월이 안 됐고, 실제 지급이 2회 이상이면
      "실제 관측 기간 -> 365일" 비율로 연환산한 추정치를 보여준다.
    - 지급이 0~1회뿐이면 연환산하지 않는다(근거 부족).
    - 상장일을 확인할 수 없으면(provider 가 모름) 이 로직 자체를 타지 않는다
      (추측 금지 원칙 유지).
    - 두 경우 모두 화면에 경고로 표시될 수 있도록 note/플래그를 남긴다.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

import config
from models.security import Security
from services.distribution_service import (
    MIN_PAYMENTS_TO_ANNUALIZE,
    compute_ttm,
)

from tests.conftest import series


def _history(listing: date, today: date, price: float = 50.0):
    return series([(listing.isoformat(), price), (today.isoformat(), price)])


def test_young_listing_with_two_payments_is_annualized(market):
    today = date.today()
    listing = today - timedelta(days=190)   # 아직 만 12개월(365일) 미만
    divs = series([
        ((listing + timedelta(days=60)).isoformat(), 1.5),
        ((listing + timedelta(days=150)).isoformat(), 1.5),
    ])
    market.set_us({"YOUNG2": {"currency": "USD", "latest": 50.0,
                              "history": _history(listing, today),
                              "distributions": divs}})
    sec = Security(market="US", ticker="YOUNG2", currency="USD")

    result = compute_ttm(sec)

    assert result.has_data
    assert result.is_estimated_annualized is True
    assert result.n_payments_ttm == 2
    assert result.actual_payment_total_native == pytest.approx(3.0)
    actual_days = (today - listing).days
    expected = 3.0 * (365.0 / actual_days)
    assert result.ttm_per_share_native == pytest.approx(expected, rel=1e-6)
    assert result.months_since_listing == pytest.approx(actual_days / 30.44, rel=1e-6)
    assert "연환산" in result.note and "2회" in result.note
    assert len(result.payments) == 2


def test_young_listing_with_one_payment_is_not_annualized(market):
    assert MIN_PAYMENTS_TO_ANNUALIZE == 2   # 이 테스트가 검증하는 전제
    today = date.today()
    listing = today - timedelta(days=120)
    divs = series([((listing + timedelta(days=30)).isoformat(), 2.0)])
    market.set_us({"YOUNG1": {"currency": "USD", "latest": 50.0,
                              "history": _history(listing, today),
                              "distributions": divs}})
    sec = Security(market="US", ticker="YOUNG1", currency="USD")

    result = compute_ttm(sec)

    assert result.has_data
    assert result.is_estimated_annualized is False
    assert result.ttm_per_share_native == pytest.approx(2.0)   # 연환산하지 않은 실측값 그대로
    assert result.n_payments_ttm == 1
    assert result.months_since_listing is not None
    assert "연환산하지 않았습니다" in result.note


def test_young_listing_with_no_payments_shows_listing_warning_not_generic(market):
    today = date.today()
    listing = today - timedelta(days=90)
    market.set_us({"YOUNGNODIV": {"currency": "USD", "latest": 50.0,
                                  "history": _history(listing, today),
                                  "distributions": None}})
    sec = Security(market="US", ticker="YOUNGNODIV", currency="USD")

    result = compute_ttm(sec)

    assert result.ttm_per_share_native == 0.0   # 실제 0 (데이터 없음이 아님)
    assert result.is_estimated_annualized is False
    assert result.months_since_listing is not None
    assert "상장" in result.note and "지급 이력이 없습니다" in result.note


def test_unknown_listing_date_does_not_trigger_annualization(market):
    """상장일을 확인할 수 없으면(get_listing_first_date 가 None) 젊은 종목 로직을
    아예 적용하지 않는다 -- 확실하지 않은 걸 '젊은 종목'이라고 단정하지 않음."""
    today = date.today()
    divs = series([
        ((today - timedelta(days=300)).isoformat(), 1.0),
        ((today - timedelta(days=200)).isoformat(), 1.0),
    ])
    # history 필드를 주지 않으면 FakeProvider.get_price_history 가 DataUnavailable 을
    # 던지고, get_listing_first_date 는 그걸 잡아 None 을 반환함 (base.py 기본 구현).
    market.set_us({"UNKNOWNLISTING": {"currency": "USD", "latest": 50.0,
                                      "distributions": divs}})
    sec = Security(market="US", ticker="UNKNOWNLISTING", currency="USD")

    result = compute_ttm(sec)

    assert result.is_estimated_annualized is False
    assert result.months_since_listing is None
    assert result.ttm_per_share_native == pytest.approx(2.0)   # 있는 그대로 합산 (기존 동작)


def test_old_listing_with_full_year_is_unaffected(market):
    today = date.today()
    listing = today - timedelta(days=2000)   # 훨씬 오래된 종목
    divs = series([
        ((today - timedelta(days=300)).isoformat(), 1.0),
        ((today - timedelta(days=200)).isoformat(), 1.0),
        ((today - timedelta(days=100)).isoformat(), 1.0),
        ((today - timedelta(days=10)).isoformat(), 1.0),
    ])
    market.set_us({"OLD4": {"currency": "USD", "latest": 50.0,
                            "history": _history(listing, today),
                            "distributions": divs}})
    sec = Security(market="US", ticker="OLD4", currency="USD")

    result = compute_ttm(sec)

    assert result.is_estimated_annualized is False
    assert result.months_since_listing is None
    assert result.ttm_per_share_native == pytest.approx(4.0)
    assert result.note == config.DISTRIBUTION_DISCLAIMER
