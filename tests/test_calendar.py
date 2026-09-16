"""분배금 달력 테스트 (네트워크 없음).

지키려는 것
-----------
1. **새 데이터를 안 받아온다.** 달을 넘겨도 이미 계산된 지급 이력만 다시 자릅니다.
2. **지나간 달과 다가올 달의 말이 다르다.** 지나간 달은 실제 지급, 앞으로는 예상.
   그리고 지나간 달도 수량은 '지금' 것이라 "받으셨습니다" 라고 하면 안 됩니다.
3. **이력이 없는 달은 숫자를 지어내지 않는다.**
"""

from __future__ import annotations

import pathlib
from datetime import date

import pytest
from streamlit.testing.v1 import AppTest

from models.portfolio import Portfolio
from models.security import Security
from services import calendar_service as cal
from services import portfolio_service
from tests.conftest import daily_series, series

APP_PATH = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")

TODAY = date(2026, 9, 15)


def _monthly(start_year: int, day: int, amount: float):
    """매달 같은 날 지급하는 이력 12개월치."""
    pairs = []
    y, m = start_year, 10
    for _ in range(12):
        pairs.append((f"{y}-{m:02d}-{day:02d}", amount))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return series(pairs)


@pytest.fixture
def comp(market):
    """미국 월배당 1 + 한국 분기배당 1 로 이뤄진 계산 결과."""
    market.set_fx(rate=1_000.0)
    market.set_us({"MON": {"currency": "USD", "latest": 100.0,
                           "distributions": _monthly(2025, 18, 0.5)}})
    market.set_kr({"458730": {"currency": "KRW", "latest": 10_000.0,
                              "distributions": series([
                                  ("2025-12-26", 100.0), ("2026-03-26", 100.0),
                                  ("2026-06-26", 100.0), ("2026-09-26", 100.0)])}})
    p = Portfolio(name="t", initial_capital_krw=10_000_000)
    p.add(Security(market="US", ticker="MON", display_name="Monthly ETF",
                   currency="USD", target_weight=0.5))
    p.add(Security(market="KR", ticker="458730", display_name="TIGER 미국배당다우존스",
                   currency="KRW", target_weight=0.5))
    return portfolio_service.compute(p)


# =====================================================================
# 달 옮기기 (순수 계산)
# =====================================================================
@pytest.mark.parametrize("y,m,delta,expected", [
    (2026, 9, 1, (2026, 10)),
    (2026, 12, 1, (2027, 1)),
    (2026, 1, -1, (2025, 12)),
    (2026, 9, 0, (2026, 9)),
    (2026, 9, -12, (2025, 9)),
])
def test_shift_month(y, m, delta, expected):
    assert cal.shift_month(y, m, delta) == expected


def test_months_between():
    assert cal.months_between((2026, 9), (2026, 12)) == 3
    assert cal.months_between((2026, 9), (2025, 9)) == -12


def test_a_day_that_does_not_exist_lands_on_the_last_day():
    """작년 3월 31일을 2월로 옮기면 2월 31일이 됩니다. 그런 날은 없습니다."""
    assert cal._clamp_day(2026, 2, 31) == date(2026, 2, 28)
    assert cal._clamp_day(2028, 2, 31) == date(2028, 2, 29)   # 윤년
    assert cal._clamp_day(2026, 9, 18) == date(2026, 9, 18)


# =====================================================================
# 어느 달을 보느냐에 따라 말이 달라진다
# =====================================================================
def test_future_months_are_called_a_forecast(comp):
    plan = cal.month_plan(comp, 2026, 11, today=TODAY)
    assert plan.basis == cal.BASIS_FORECAST
    assert "예상" in plan.title


def test_this_month_is_still_a_forecast(comp):
    """이번 달은 이미 지급된 것도 있지만, 한 달 안에서 실제와 예상을 섞으면
    어느 줄이 어느 쪽인지 알 수 없게 됩니다. 달 단위로 딱 가릅니다."""
    plan = cal.month_plan(comp, 2026, 9, today=TODAY)
    assert plan.basis == cal.BASIS_FORECAST


def test_past_months_are_actual_payments(comp):
    plan = cal.month_plan(comp, 2026, 7, today=TODAY)
    assert plan.basis == cal.BASIS_ACTUAL
    assert "실제 지급" in plan.title


def test_the_title_always_says_it_is_before_tax(comp):
    """이 화면은 '이번 달에 얼마 들어오나' 라서 통장에 찍힐 금액으로 읽힙니다.
    실제로는 배당소득세를 뗍니다. 밑에 작게 적으면 안 읽히고, 그림으로 퍼지면
    더더욱 안 읽히므로 제목에 붙여 같이 다니게 합니다."""
    for year, month in [(2026, 11), (2026, 9), (2026, 7)]:
        assert "(세전)" in cal.month_plan(comp, year, month, today=TODAY).title


def test_beyond_the_history_we_refuse_to_make_numbers_up(comp):
    plan = cal.month_plan(comp, 2028, 1, today=TODAY)
    assert not plan.in_range
    assert plan.entries == []
    assert plan.total_krw == 0.0


def test_you_cannot_page_past_the_history(comp):
    assert cal.can_go(comp, 2026, 9, +1, today=TODAY)
    assert not cal.can_go(comp, 2027, 9, +1, today=TODAY)     # +12 가 끝
    assert not cal.can_go(comp, 2025, 9, -1, today=TODAY)


# =====================================================================
# 내용
# =====================================================================
def test_a_monthly_payer_shows_up_every_month(comp):
    for month in (6, 7, 8):          # 지나간 달 (실제)
        plan = cal.month_plan(comp, 2026, month, today=TODAY)
        assert "MON" in [e.ticker for e in plan.entries], f"{month}월"
        assert "MON" not in plan.silent, f"{month}월"


def test_a_quarterly_payer_is_listed_as_silent_in_the_off_months(comp):
    """분기배당만 담으면 세 달 중 두 달은 0원인데, 대부분 짜고 나서야 압니다."""
    plan = cal.month_plan(comp, 2026, 7, today=TODAY)
    assert "TIGER 미국배당다우존스" in plan.silent
    assert "TIGER 미국배당다우존스" not in [e.label for e in plan.entries]


def test_a_quarterly_payer_shows_up_in_its_month(comp):
    plan = cal.month_plan(comp, 2026, 6, today=TODAY)
    assert "TIGER 미국배당다우존스" in [e.label for e in plan.entries]


def test_amounts_are_shares_times_per_share_in_won(comp):
    plan = cal.month_plan(comp, 2026, 7, today=TODAY)
    row = next(r for r in comp.rows if r.security.ticker == "MON")
    entry = next(e for e in plan.entries if e.ticker == "MON")
    assert entry.amount_krw == pytest.approx(row.shares * 0.5 * 1_000.0)


def test_entries_are_sorted_by_day(comp):
    plan = cal.month_plan(comp, 2026, 6, today=TODAY)
    days = [e.day for e in plan.entries]
    assert days == sorted(days)


def test_a_forecast_month_borrows_last_years_same_month(comp):
    """작년 10월 기록이 올해 10월 예상이 됩니다."""
    plan = cal.month_plan(comp, 2026, 10, today=TODAY)
    assert plan.basis == cal.BASIS_FORECAST
    assert [e.ticker for e in plan.entries] == ["MON"]
    assert all(e.day.year == 2026 and e.day.month == 10 for e in plan.entries)


def test_securities_excluded_from_distribution_are_left_out(market):
    market.set_fx(rate=1_000.0)
    market.set_us({"MON": {"currency": "USD", "latest": 100.0,
                           "distributions": _monthly(2025, 18, 0.5)}})
    p = Portfolio(name="t", initial_capital_krw=10_000_000)
    sec = Security(market="US", ticker="MON", currency="USD", target_weight=0.5)
    sec.distribution_enabled = False
    p.add(sec)
    plan = cal.month_plan(portfolio_service.compute(p), 2026, 7, today=TODAY)
    assert plan.entries == [] and plan.silent == []


def test_without_an_exchange_rate_us_securities_are_missing_and_we_say_why(market):
    """환율이 없으면 미국 종목은 수량조차 계산이 안 됩니다(원화 가격을 모름).

    그러면 달력에서 조용히 사라지는데, 아무 말이 없으면 "왜 미국 종목이 안 보이지?"
    가 됩니다. 사라진 이유를 달력이 직접 말해야 합니다.
    """
    market.set_fx(ok=False)
    market.set_us({"MON": {"currency": "USD", "latest": 100.0,
                           "distributions": _monthly(2025, 18, 0.5)}})
    p = Portfolio(name="t", initial_capital_krw=10_000_000)
    p.add(Security(market="US", ticker="MON", currency="USD", target_weight=0.5))
    plan = cal.month_plan(portfolio_service.compute(p), 2026, 7, today=TODAY)
    assert plan.fx_missing, "환율 때문에 빠졌다는 표시가 없습니다"
    assert plan.entries == []


def test_no_exchange_rate_complaint_when_everything_is_korean(market):
    """한국 종목만 담았으면 환율은 아무 상관이 없습니다. 괜한 경고를 띄우면 안 됩니다."""
    market.set_fx(ok=False)
    market.set_kr({"458730": {"currency": "KRW", "latest": 10_000.0,
                              "distributions": series([("2026-07-26", 100.0)])}})
    p = Portfolio(name="t", initial_capital_krw=10_000_000)
    p.add(Security(market="KR", ticker="458730", display_name="TIGER 미국배당다우존스",
                   currency="KRW", target_weight=0.5))
    plan = cal.month_plan(portfolio_service.compute(p), 2026, 7, today=TODAY)
    assert not plan.fx_missing
    assert len(plan.entries) == 1


def test_an_empty_portfolio_produces_an_empty_month(market):
    plan = cal.month_plan(portfolio_service.compute(Portfolio(name="t")),
                          2026, 9, today=TODAY)
    assert plan.entries == [] and plan.total_krw == 0.0


# =====================================================================
# 화면
# =====================================================================
def _market_for_app(market):
    market.set_fx(rate=1_000.0)
    market.set_us({"MON": {"currency": "USD", "latest": 100.0,
                           "distributions": _monthly(2025, 18, 0.5)}})


def _app(market):
    _market_for_app(market)
    p = Portfolio(name="t", initial_capital_krw=10_000_000)
    p.add(Security(market="US", ticker="MON", currency="USD", target_weight=0.5))
    at = AppTest.from_file(APP_PATH, default_timeout=90)
    at.session_state["portfolio"] = p
    return at.run()


def test_the_calendar_button_is_hidden_when_nothing_is_held(market):
    _market_for_app(market)
    at = AppTest.from_file(APP_PATH, default_timeout=90).run()
    assert not [b for b in at.button if b.key == "cal_open_btn"]


def test_opening_the_calendar_does_not_crash(market):
    at = _app(market)
    [b for b in at.button if b.key == "cal_open_btn"][0].click().run()
    assert not at.exception
    assert at.session_state["cal_open"] is True


def test_paging_months_changes_the_month_in_the_same_render(market):
    """달을 넘기는 버튼을 나중에 읽으면 한 박자 늦게 바뀝니다."""
    at = _app(market)
    [b for b in at.button if b.key == "cal_open_btn"][0].click().run()
    start = at.session_state["cal_ym"]

    [b for b in at.button if b.key == "cal_next"][0].click().run()
    assert not at.exception
    assert at.session_state["cal_ym"] == cal.shift_month(*start, 1)

    [b for b in at.button if b.key == "cal_prev"][0].click().run()
    assert at.session_state["cal_ym"] == start


def test_closing_the_calendar_puts_it_away(market):
    at = _app(market)
    [b for b in at.button if b.key == "cal_open_btn"][0].click().run()
    [b for b in at.button if b.key == "cal_close"][0].click().run()
    assert not at.exception
    assert at.session_state["cal_open"] is False
