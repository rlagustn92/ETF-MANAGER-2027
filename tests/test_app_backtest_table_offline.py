"""백테스트 결과 표 테스트 (네트워크 없음).

사용자 요청으로 '살 때 원금(₩)' 칸을 추가했습니다 = 그때 매수가 x 수량 (원화 환산).
표에 적힌 값이 실제로 투자된 금액과 다르면 안 되므로, 화면 값과 계산 결과를 맞춰봅니다.
"""

from __future__ import annotations

import pathlib
from datetime import date

import pytest
from streamlit.testing.v1 import AppTest

from models.portfolio import Portfolio
from models.security import Security
from tests.conftest import series

APP_PATH = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")


def _run_backtest_in_app(market):
    # 한국 종목: 5만원 -> 10만원, 미국 종목: $50 -> $100 (환율 1,000원 고정)
    market.set_fx(rate=1_000.0)
    market.set_kr({"A": {"currency": "KRW",
                         "history": series([("2021-01-04", 50_000.0),
                                            ("2026-09-10", 100_000.0)])}})
    market.set_us({"B": {"currency": "USD",
                         "history": series([("2021-01-04", 50.0),
                                            ("2026-09-10", 100.0)])}})

    p = Portfolio(name="bt", initial_capital_krw=10_000_000)
    p.add(Security(market="KR", ticker="A", currency="KRW", target_weight=0.60))
    p.add(Security(market="US", ticker="B", currency="USD", target_weight=0.40))

    at = AppTest.from_file(APP_PATH, default_timeout=90)
    at.session_state["portfolio"] = p
    at.run()

    [d for d in at.date_input if d.label == "시작일"][0].set_value(date(2021, 1, 4)).run()
    [b for b in at.button if b.label == "실행하기"][0].click().run()
    assert not at.exception
    return at


def _backtest_table(at):
    # 화면에는 '어떻게 살까?' 표와 백테스트 표가 있는데, 뒤엣것이 백테스트 결과
    tables = [df.value for df in at.dataframe if "살 때 원금(₩)" in df.value.columns]
    assert tables, "백테스트 결과 표를 찾지 못했습니다."
    return tables[0]


def test_backtest_table_has_principal_column_matching_shares_times_buy_price(market):
    at = _run_backtest_in_app(market)
    df = _backtest_table(at)

    rows = {r.ticker: r for r in at.session_state["bt_result"].rows}
    for _, line in df.iterrows():
        row = rows[line["종목"]]
        # 살 때 원금 = 그때 매수가(원화 환산) x 수량
        assert line["살 때 원금(₩)"] == f"{row.shares * row.buy_price_krw:,.0f}"
        assert line["살 때 원금(₩)"] == f"{row.invested_krw:,.0f}"


def test_principal_column_sums_to_the_reported_total(market):
    """종목별 '살 때 원금' 합계가 위에 표시되는 '총 원금'과 같아야 한다."""
    at = _run_backtest_in_app(market)
    df = _backtest_table(at)

    total_in_rows = sum(int(v.replace(",", "")) for v in df["살 때 원금(₩)"])
    result = at.session_state["bt_result"]
    assert total_in_rows == round(result.total_invested_krw)

    texts = " ".join(w.value for w in at.markdown) + " ".join(
        str(w.value) for w in at.text)
    assert f"총 원금: ₩{result.total_invested_krw:,.0f}" in texts


def test_korean_rows_show_the_name_not_the_stock_code(market):
    """한국 종목은 티커가 종목코드(예: 458730)라서, 그대로 찍으면 백테스트 표에
    "458730" 만 떠서 뭘 돌린 건지 알 수가 없습니다. 실제로 그렇게 떴던 버그입니다.
    위 '어떻게 살까?' 표와 같은 규칙(한국=이름, 미국=티커)이어야 합니다."""
    market.set_fx(rate=1_000.0)
    market.set_kr({"458730": {"currency": "KRW",
                              "history": series([("2021-01-04", 10_000.0),
                                                 ("2026-09-10", 12_000.0)])}})
    market.set_us({"SCHD": {"currency": "USD",
                            "history": series([("2021-01-04", 70.0),
                                               ("2026-09-10", 90.0)])}})
    p = Portfolio(name="bt", initial_capital_krw=10_000_000)
    p.add(Security(market="KR", ticker="458730", name="TIGER 미국배당다우존스",
                   display_name="TIGER 미국배당다우존스", currency="KRW", target_weight=0.5))
    p.add(Security(market="US", ticker="SCHD", currency="USD", target_weight=0.5))

    at = AppTest.from_file(APP_PATH, default_timeout=90)
    at.session_state["portfolio"] = p
    at.run()
    [d for d in at.date_input if d.label == "시작일"][0].set_value(date(2021, 1, 4)).run()
    [b for b in at.button if b.label == "실행하기"][0].click().run()
    assert not at.exception

    names = list(_backtest_table(at)["종목"])
    assert "TIGER 미국배당다우존스" in names, names
    assert "458730" not in names, names
    assert "SCHD" in names, names          # 미국은 티커 그대로


def test_table_shows_both_buy_and_valuation_fx(market):
    """'살 때 환율'(그때) 과 '지금 환율'(평가 시점) 을 나란히 보여줘야, 수익 중 얼마가
    환율 때문인지 알 수 있습니다. 원화 종목은 환율이 없으므로 '–'."""
    at = _run_backtest_in_app(market)
    df = _backtest_table(at)

    us_line = df[df["종목"] == "B"].iloc[0]
    assert us_line["살 때 환율"] == "1,000.00"
    assert us_line["지금 환율"] == "1,000.00"

    kr_line = df[df["종목"] == "A"].iloc[0]
    assert kr_line["살 때 환율"] == "–"
    assert kr_line["지금 환율"] == "–"


def test_valuation_fx_matches_the_rate_used_for_the_valuation(market):
    """표의 '지금 환율' 은 평가금액을 실제로 계산할 때 쓴 환율과 같아야 한다."""
    at = _run_backtest_in_app(market)
    df = _backtest_table(at)

    row = next(r for r in at.session_state["bt_result"].rows if r.ticker == "B")
    assert df[df["종목"] == "B"].iloc[0]["지금 환율"] == f"{row.final_fx:,.2f}"
    # 평가금액 = 수량 x 종료가 x 지금 환율
    assert row.final_value_krw == row.shares * row.final_price_native * row.final_fx


def test_backtest_shows_return_on_invested_money_not_diluted_by_cash(market):
    """시드의 일부만 담으면 '전체 기준' 수익률은 현금에 희석됩니다.
    화면에 크게 보이는 값은 '투자금 기준'(= 손익 / 실제 투자금) 이어야 합니다.
    (제보 사례: 종목은 +21% 인데 화면엔 +0.97% 로 보였음)"""
    at = _run_backtest_in_app(market)
    r = at.session_state["bt_result"]

    on_invested = r.profit_krw / r.total_invested_krw * 100.0
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["수익률 (투자금 기준)"] == f"{on_invested:+.2f}%"

    # 관계식: 전체 기준 = 투자금 기준 x (투자금 / 초기투자금)
    ratio = r.total_invested_krw / r.initial_capital_krw
    assert r.return_pct == pytest.approx(on_invested * ratio, abs=1e-6)


def test_backtest_warns_when_most_of_the_money_stayed_in_cash(market):
    """대부분이 현금으로 남았으면 그 사실을 눈에 띄게 알려줘야 합니다."""
    market.set_fx(rate=1_000.0)
    market.set_kr({"A": {"currency": "KRW",
                         "history": series([("2021-01-04", 50_000.0),
                                            ("2026-09-10", 100_000.0)])}})
    p = Portfolio(name="bt", initial_capital_krw=100_000_000)
    p.add(Security(market="KR", ticker="A", currency="KRW", target_weight=0.05))

    at = AppTest.from_file(APP_PATH, default_timeout=90)
    at.session_state["portfolio"] = p
    at.run()
    [d for d in at.date_input if d.label == "시작일"][0].set_value(date(2021, 1, 4)).run()
    [b for b in at.button if b.label == "실행하기"][0].click().run()
    assert not at.exception

    notes = [m.value for m in at.markdown if m.value.startswith("<div class='note'>")]
    assert notes, "현금이 많이 남았으면 안내가 떠야 합니다."
    assert "현금" in notes[0] and "전체 기준" in notes[0]


def test_principal_is_in_krw_even_for_us_securities(market):
    """미국 종목도 '살 때 원금'은 그때 환율로 환산한 원화여야 한다 (달러가 아니라)."""
    at = _run_backtest_in_app(market)
    df = _backtest_table(at)

    us_line = df[df["종목"] == "B"].iloc[0]
    us_row = next(r for r in at.session_state["bt_result"].rows if r.ticker == "B")
    # $50 x 환율 1,000 = 1주당 50,000원
    assert us_row.buy_price_krw == 50_000.0
    assert us_line["살 때 원금(₩)"] == f"{us_row.shares * 50_000:,.0f}"
