"""backtest_service 테스트 (네트워크 없음). 인수인계서 66~77, 115."""

from datetime import date

import pandas as pd
import pytest

from models.portfolio import Portfolio
from models.security import Security
from services import backtest_service

from tests.conftest import daily_series, series


def _hist(mapping: dict[str, float]) -> pd.Series:
    return series(list(mapping.items()))


def test_buy_and_hold_basic_krw(market):
    hist = _hist({"2021-01-04": 50_000, "2023-01-02": 80_000, "2026-09-10": 100_000})
    market.set_kr({"A": {"currency": "KRW", "history": hist}})
    p = Portfolio(name="bt", initial_capital_krw=10_000_000)
    p.add(Security(market="KR", ticker="A", currency="KRW", target_weight=1.0))
    res = backtest_service.run_backtest(p, date(2021, 1, 4))
    assert res.ok
    assert res.actual_buy_date == date(2021, 1, 4)
    assert res.data_as_of == date(2026, 9, 10)
    # 목표금액 10,000,000 / 50,000 = 200주, 실제투자 10,000,000, 현금 0
    assert res.rows[0].shares == 200
    assert res.total_invested_krw == 10_000_000
    assert res.cash_balance_krw == 0
    # 평가 200 * 100,000 = 20,000,000 -> 수익률 +100%
    assert res.final_value_krw == pytest.approx(20_000_000)
    assert res.return_pct == pytest.approx(100.0)


def test_non_trading_start_moves_to_next_common_day(market):
    hist = _hist({"2022-01-03": 100.0, "2026-09-10": 200.0})
    market.set_kr({"A": {"currency": "KRW", "history": hist}})
    p = Portfolio(name="bt", initial_capital_krw=1_000_000)
    p.add(Security(market="KR", ticker="A", currency="KRW", target_weight=1.0))
    res = backtest_service.run_backtest(p, date(2022, 1, 1))   # 신정 휴장
    assert res.ok
    assert res.input_start == date(2022, 1, 1)
    assert res.actual_buy_date == date(2022, 1, 3)
    assert any("2022-01-03" in w for w in res.warnings)


def test_security_listed_after_start_blocks_backtest(market):
    a = _hist({"2021-01-04": 100.0, "2026-09-10": 150.0})
    b = _hist({"2024-02-01": 20.0, "2026-09-10": 25.0})   # 2024 상장
    market.set_kr({"OLD": {"currency": "KRW", "history": a},
                   "NEW": {"currency": "KRW", "history": b}})
    p = Portfolio(name="bt", initial_capital_krw=1_000_000)
    p.add(Security(market="KR", ticker="OLD", currency="KRW", target_weight=0.5))
    p.add(Security(market="KR", ticker="NEW", currency="KRW", target_weight=0.5))
    res = backtest_service.run_backtest(p, date(2021, 1, 4))
    assert res.ok is False
    assert "상장" in res.message and "NEW" in res.message


def test_late_listing_message_suggests_a_start_date_that_works(market):
    """'안 된다'로만 끝내면 어느 날짜로 바꿔야 할지 사용자가 직접 찾아야 합니다.
    가장 늦게 상장한 종목 날짜를 알려줘야 합니다 (예시 포트폴리오는 신생 ETF 가 섞여
    있어서 기본 시작일로는 거의 항상 막힙니다)."""
    # 실제 시세처럼 매일 값이 있어야 "상장일 이후 구간"이 제대로 판정됩니다
    market.set_kr({
        "OLD": {"currency": "KRW", "history": daily_series("2021-01-04", "2026-09-10", 100.0)},
        "MID": {"currency": "KRW", "history": daily_series("2023-06-20", "2026-09-10", 20.0)},
        "NEW": {"currency": "KRW", "history": daily_series("2024-02-01", "2026-09-10", 10.0)},
    })
    p = Portfolio(name="bt", initial_capital_krw=3_000_000)
    for t in ("OLD", "MID", "NEW"):
        p.add(Security(market="KR", ticker=t, currency="KRW", target_weight=1 / 3))

    res = backtest_service.run_backtest(p, date(2021, 1, 4))
    assert res.ok is False
    assert "2024-02-01" in res.message            # 전부 포함되는 가장 이른 날
    assert "이후로 잡으면" in res.message

    # 화면이 버튼 하나로 고쳐줄 수 있게 날짜를 값으로도 내보내야 한다.
    # 글자로만 있으면 사용자가 직접 옮겨 적어야 한다.
    assert res.suggested_start == date(2024, 2, 1)

    # 안내한 날짜로 다시 돌리면 실제로 성공해야 한다
    ok = backtest_service.run_backtest(p, res.suggested_start)
    assert ok.ok is True, ok.message
    assert ok.suggested_start is None             # 성공했으면 고칠 게 없다


def test_late_listing_message_uses_korean_names_not_stock_codes(market):
    """한국 종목은 티커가 종목코드라, 그대로 쓰면 '어떤 종목이 늦게 상장했는지'
    사용자가 알 수 없습니다."""
    market.set_kr({
        "458730": {"currency": "KRW",
                   "history": daily_series("2021-01-04", "2026-09-10", 100.0)},
        "498400": {"currency": "KRW",
                   "history": daily_series("2024-11-01", "2026-09-10", 10.0)},
    })
    p = Portfolio(name="bt", initial_capital_krw=2_000_000)
    p.add(Security(market="KR", ticker="458730", name="TIGER 미국배당다우존스",
                   display_name="TIGER 미국배당다우존스", currency="KRW", target_weight=0.5))
    p.add(Security(market="KR", ticker="498400", name="KODEX 200타겟위클리커버드콜",
                   display_name="KODEX 200타겟위클리커버드콜", currency="KRW", target_weight=0.5))

    res = backtest_service.run_backtest(p, date(2021, 1, 4))
    assert res.ok is False
    assert "KODEX 200타겟위클리커버드콜" in res.message, res.message
    assert "498400" not in res.message, res.message


def test_us_backtest_uses_past_fx_not_current(market):
    # 과거 환율 1,000 / 현재 환율 2,000 : 반드시 과거 환율로 매수해야 함
    fx_hist = pd.Series(
        [1_000.0, 1_000.0, 2_000.0, 2_000.0],
        index=pd.DatetimeIndex(["2021-01-04", "2021-06-01", "2026-09-01", "2026-09-10"], name="date"),
    )
    market.set_fx(history=fx_hist)
    price = _hist({"2021-01-04": 100.0, "2026-09-10": 100.0})   # 달러 가격은 변화 없음
    market.set_us({"USX": {"currency": "USD", "history": price}})
    p = Portfolio(name="bt", initial_capital_krw=10_000_000)
    p.add(Security(market="US", ticker="USX", currency="USD", target_weight=1.0))
    res = backtest_service.run_backtest(p, date(2021, 1, 4))
    assert res.ok
    row = res.rows[0]
    assert row.buy_fx == 1_000.0
    assert row.buy_price_krw == 100_000            # 100 x 1000
    assert row.shares == 100                       # 10,000,000 / 100,000
    # 종료 평가: 100주 x $100 x 2000 = 20,000,000 -> 환율만으로 +100%
    assert res.final_value_krw == pytest.approx(20_000_000)
    assert res.return_pct == pytest.approx(100.0)


def test_split_adjusted_series_not_double_counted(market):
    # 공급되는 종가는 이미 분할 소급반영된 계열. splits 정보가 있어도 수량에 곱하지 않는다.
    price = _hist({"2020-01-02": 10.0, "2026-09-10": 40.0})
    splits = series([("2021-07-20", 4.0), ("2024-06-10", 10.0)])
    market.set_kr({"SPL": {"currency": "KRW", "history": price, "splits": splits}})
    p = Portfolio(name="bt", initial_capital_krw=10_000_000)
    p.add(Security(market="KR", ticker="SPL", currency="KRW", target_weight=1.0))
    res = backtest_service.run_backtest(p, date(2020, 1, 2))
    row = res.rows[0]
    assert row.shares == 1_000_000               # 10,000,000 / 10
    assert row.splits_in_period == 2             # 참고 정보만
    # 평가: 1,000,000주 x 40 = 40,000,000 (분할비율 40배를 추가로 곱하지 않음)
    assert res.final_value_krw == pytest.approx(40_000_000)
    assert res.return_pct == pytest.approx(300.0)


def test_distributions_option_adds_cash_not_reinvested(market):
    price = _hist({"2021-01-04": 100.0, "2026-09-10": 100.0})
    divs = series([("2022-01-15", 5.0), ("2023-01-15", 5.0)])
    market.set_kr({"D": {"currency": "KRW", "history": price, "distributions": divs}})
    p = Portfolio(name="bt", initial_capital_krw=1_000_000)
    p.add(Security(market="KR", ticker="D", currency="KRW", target_weight=1.0))

    base = backtest_service.run_backtest(p, date(2021, 1, 4))
    assert base.final_value_krw == pytest.approx(1_000_000)   # 가격 불변

    withd = backtest_service.run_backtest(p, date(2021, 1, 4), include_distributions=True)
    # 10,000주 x (5 + 5) = 100,000 현금 추가
    assert withd.distributions_cash_krw == pytest.approx(100_000)
    assert withd.final_value_krw == pytest.approx(1_100_000)


def test_price_data_unavailable_returns_error_not_exception(market):
    market.set_kr({"A": {"currency": "KRW", "history": "error"}})
    p = Portfolio(name="bt", initial_capital_krw=1_000_000)
    p.add(Security(market="KR", ticker="A", currency="KRW", target_weight=1.0))
    res = backtest_service.run_backtest(p, date(2021, 1, 4))
    assert res.ok is False
    assert res.message
