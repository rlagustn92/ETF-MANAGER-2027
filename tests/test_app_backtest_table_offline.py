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
from tests.conftest import daily_series, series

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


def test_one_click_fixes_a_too_early_start_date(market):
    """상장이 늦은 종목 때문에 막혔을 때, 사용자가 날짜를 직접 옮겨 적지 않아도
    버튼 한 번으로 고쳐서 다시 돌아가야 합니다 (사용자 요청)."""
    market.set_fx(rate=1_000.0)
    market.set_kr({
        "458730": {"currency": "KRW",
                   "history": daily_series("2021-01-04", "2026-09-10", 10_000.0)},
        "498400": {"currency": "KRW",
                   "history": daily_series("2024-11-01", "2026-09-10", 20_000.0)},
    })
    p = Portfolio(name="bt", initial_capital_krw=10_000_000)
    p.add(Security(market="KR", ticker="458730", display_name="TIGER 미국배당다우존스",
                   currency="KRW", target_weight=0.5))
    p.add(Security(market="KR", ticker="498400", display_name="KODEX 200타겟위클리커버드콜",
                   currency="KRW", target_weight=0.5))

    at = AppTest.from_file(APP_PATH, default_timeout=90)
    at.session_state["portfolio"] = p
    at.run()
    [d for d in at.date_input if d.label == "시작일"][0].set_value(date(2021, 1, 4)).run()
    [b for b in at.button if b.label == "실행하기"][0].click().run()
    assert not at.exception
    assert at.session_state["bt_result"].ok is False

    # 📅 로 시작하는 버튼이 화면에 여럿 있습니다(분배금 달력 등). key 로 짚습니다.
    fix = [b for b in at.button if b.key == "bt_fix_start"]
    assert fix, "날짜를 고쳐주는 버튼이 없습니다"
    assert "2024-11-01" in fix[0].label

    fix[0].click().run()
    assert not at.exception
    # 날짜가 바뀌고, 다시 누르지 않아도 백테스트가 성공해 있어야 한다
    assert at.session_state["bt_start"] == date(2024, 11, 1)
    assert at.session_state["bt_result"].ok is True, at.session_state["bt_result"].message
    assert not [b for b in at.button if b.key == "bt_fix_start"]


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

    # 백테스트 결과 위에는 한 문장 요약도 같은 모양(.note)으로 붙습니다.
    # 그래서 첫 번째가 아니라 "현금 안내" 를 골라서 봅니다.
    notes = [m.value for m in at.markdown if m.value.startswith("<div class='note'>")]
    cash_note = [n for n in notes if "현금" in n]
    assert cash_note, f"현금이 많이 남았으면 안내가 떠야 합니다. 있는 것: {notes}"
    assert "전체 기준" in cash_note[0]


# =====================================================================
# 분배금은 기본으로 켜둔다 (사용자 요청)
# =====================================================================
def _dividend_app(market):
    """분배금이 실제로 나오는 종목 하나짜리 앱."""
    market.set_fx(rate=1_000.0)
    market.set_kr({"A": {
        "currency": "KRW",
        # 중간에 반토막 나는 구간을 넣어 둡니다 -- 낙폭 문구를 검사하려면 낙폭이
        # 실제로 있어야 합니다. 없으면 그 테스트는 아무것도 확인하지 않습니다.
        "history": series([("2021-01-04", 50_000.0), ("2022-06-01", 80_000.0),
                           ("2023-01-04", 40_000.0), ("2026-09-10", 100_000.0)]),
        "distributions": series([(f"{y}-{m:02d}-15", 500.0)
                                 for y in range(2021, 2027) for m in (3, 6, 9, 12)]),
    }})
    p = Portfolio(name="bt", initial_capital_krw=10_000_000)
    p.add(Security(market="KR", ticker="A", currency="KRW", target_weight=1.0))

    at = AppTest.from_file(APP_PATH, default_timeout=90)
    at.session_state["portfolio"] = p
    at.run()
    return at


def _backtest_checkbox(at):
    return [c for c in at.checkbox if c.label.startswith("분배금 포함")][0]


def test_distributions_are_included_by_default(market):
    """여기 오는 사람은 대부분 배당 포트폴리오를 짭니다. 분배금을 빼면 그 구성의
    핵심 수익원이 통째로 빠진 숫자가 되고, 고배당 ETF 가 성장주 ETF 에 항상 지는
    것처럼 보입니다 (돌려준 몫이 주가에서 빠져 있으니까요)."""
    at = _dividend_app(market)
    assert _backtest_checkbox(at).value is True


def test_the_headline_says_what_is_inside_the_number(market):
    """켜두는 게 기본이면, 저 금액에 분배금이 들어 있다는 걸 같이 말해야 합니다.
    안 그러면 주가만 계산한 다른 곳 숫자와 나란히 놓고 비교됩니다."""
    at = _dividend_app(market)
    [d for d in at.date_input if d.label == "시작일"][0].set_value(date(2021, 1, 4)).run()
    [b for b in at.button if b.label == "실행하기"][0].click().run()
    assert not at.exception

    r = at.session_state["bt_result"]
    assert r.ok and r.include_distributions and r.distributions_cash_krw > 0

    notes = " ".join(m.value for m in at.markdown
                     if m.value.startswith("<div class='note'>"))
    assert "분배금" in notes and "세전" in notes

    # 합계 한 칸에 뭉치지 않고 쪼개서 보여줍니다 (사용자 요청).
    metrics = {m.label: m.value for m in at.metric}
    for label in ("최종 자산 (합계)", "주식 평가액", "받은 분배금 (세전)"):
        assert label in metrics, list(metrics)
    assert metrics["최종 자산 (합계)"] == f"₩{r.final_value_krw:,.0f}"
    assert metrics["주식 평가액"] == f"₩{r.holdings_value_krw:,.0f}"
    assert metrics["받은 분배금 (세전)"] == f"₩{r.distributions_cash_krw:,.0f}"
    # 쪼갠 셋을 더하면 화면의 합계와 **정확히** 같아야 합니다.
    assert (r.holdings_value_krw + r.cash_balance_krw
            + r.distributions_cash_krw) == pytest.approx(r.final_value_krw, abs=1e-6)


def test_the_screen_says_the_drawdown_excludes_the_dividend_cash(market):
    """낙폭은 쌓인 분배금을 빼고 잽니다. 같은 화면에 기준이 다른 두 숫자가 나란히
    있으니, 말해두지 않으면 어긋나 보입니다."""
    at = _dividend_app(market)
    [d for d in at.date_input if d.label == "시작일"][0].set_value(date(2021, 1, 4)).run()
    [b for b in at.button if b.label == "실행하기"][0].click().run()
    r = at.session_state["bt_result"]
    if r.max_drawdown_pct >= 0:
        pytest.skip("이 표본에서는 낙폭이 잡히지 않습니다")
    notes = " ".join(m.value for m in at.markdown
                     if m.value.startswith("<div class='note'>"))
    assert "빼고 잰" in notes


def test_turning_it_off_still_works(market):
    """기본값을 바꾼 것뿐입니다. 끄면 주가만 본 숫자가 나와야 합니다."""
    at = _dividend_app(market)
    [d for d in at.date_input if d.label == "시작일"][0].set_value(date(2021, 1, 4)).run()
    _backtest_checkbox(at).set_value(False).run()
    [b for b in at.button if b.label == "실행하기"][0].click().run()
    assert not at.exception

    r = at.session_state["bt_result"]
    assert r.include_distributions is False
    metrics = {m.label: m.value for m in at.metric}
    assert "받은 분배금 (세전)" not in metrics, list(metrics)
    # 꺼도 쪼개기는 그대로 -- 주식 평가액 + 잔여현금 = 합계
    assert (r.holdings_value_krw + r.cash_balance_krw) == pytest.approx(
        r.final_value_krw, abs=1e-6)
    assert metrics["주식 평가액"] == f"₩{r.holdings_value_krw:,.0f}"


def test_principal_is_in_krw_even_for_us_securities(market):
    """미국 종목도 '살 때 원금'은 그때 환율로 환산한 원화여야 한다 (달러가 아니라)."""
    at = _run_backtest_in_app(market)
    df = _backtest_table(at)

    us_line = df[df["종목"] == "B"].iloc[0]
    us_row = next(r for r in at.session_state["bt_result"].rows if r.ticker == "B")
    # $50 x 환율 1,000 = 1주당 50,000원
    assert us_row.buy_price_krw == 50_000.0
    assert us_line["살 때 원금(₩)"] == f"{us_row.shares * 50_000:,.0f}"
