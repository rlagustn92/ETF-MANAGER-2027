"""구성 막대 · 성향 라벨 · 최대낙폭 테스트.

여기서 지키는 것
----------------
1. **평가가 아니라 거울.** 성향 라벨은 점수도 등급도 아니고, 왜 그렇게 봤는지를
   항상 같이 말합니다. "빼세요/담으세요" 는 없습니다.
2. **모르면 모른다고 한다.** 유형 사전에 없는 종목은 "기타" 입니다.
3. **수익만 보여주지 않는다.** 백테스트 한 줄 요약에는 최대낙폭이 같이 붙습니다.
   수익만 크게 쓰면 앱이 아니라 광고가 됩니다.
"""

from __future__ import annotations

import pathlib
from datetime import date

import pytest
from streamlit.testing.v1 import AppTest

from models.portfolio import Portfolio
from models.security import Security
from services import backtest_service, portfolio_service
from services import composition_service as cs
from tests.conftest import series

APP_PATH = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")


# =====================================================================
# 유형 분류
# =====================================================================
@pytest.mark.parametrize("ticker,expected", [
    ("SCHD", cs.KIND_DIVIDEND), ("VOO", cs.KIND_DIVIDEND),
    ("JEPQ", cs.KIND_COVERED_CALL), ("QYLD", cs.KIND_COVERED_CALL),
    ("TLT", cs.KIND_BOND), ("SGOV", cs.KIND_BOND),
    ("O", cs.KIND_REIT), ("VNQ", cs.KIND_REIT),
    ("schd", cs.KIND_DIVIDEND),                 # 소문자도
])
def test_us_kinds_come_from_the_dictionary(ticker, expected):
    assert cs.classify_kind("US", ticker) == expected


@pytest.mark.parametrize("name,expected", [
    ("TIGER 미국나스닥100커버드콜", cs.KIND_COVERED_CALL),
    ("KODEX 200타겟위클리커버드콜", cs.KIND_COVERED_CALL),
    ("KODEX 종합채권(AA-이상)액티브", cs.KIND_BOND),
    ("TIGER 국채30년", cs.KIND_BOND),
    ("TIGER 리츠부동산인프라", cs.KIND_REIT),
    ("TIGER 미국배당다우존스", cs.KIND_DIVIDEND),
    ("PLUS 고배당주", cs.KIND_DIVIDEND),
])
def test_korean_kinds_come_from_the_name(name, expected):
    assert cs.classify_kind("KR", "123456", name) == expected


def test_unknown_securities_are_called_other_not_guessed():
    """사전에 없는 걸 아무 종류로나 밀어 넣으면 막대가 거짓말을 합니다."""
    assert cs.classify_kind("US", "ZZZZ") == cs.KIND_OTHER
    assert cs.classify_kind("KR", "123456", "이름없는상품") == cs.KIND_OTHER
    assert cs.classify_kind("US", "") == cs.KIND_OTHER


# =====================================================================
# 분배주기 -- 사전이 아니라 지급 횟수로
# =====================================================================
@pytest.mark.parametrize("n,expected", [
    (52, cs.SCHEDULE_WEEKLY), (48, cs.SCHEDULE_WEEKLY),
    (12, cs.SCHEDULE_MONTHLY), (11, cs.SCHEDULE_MONTHLY),
    (4, cs.SCHEDULE_QUARTERLY), (3, cs.SCHEDULE_QUARTERLY),
    (2, cs.SCHEDULE_RARE), (1, cs.SCHEDULE_RARE),
    (0, cs.SCHEDULE_NONE),
])
def test_schedule_is_counted_from_the_data(n, expected):
    assert cs.classify_schedule(n) == expected


def test_schedule_handles_junk():
    assert cs.classify_schedule(None) == cs.SCHEDULE_NONE


# =====================================================================
# 막대
# =====================================================================
def _comp(market, holdings):
    """holdings: [(market, ticker, name, weight, n_payments)]"""
    market.set_fx(rate=1_000.0)
    us, kr = {}, {}
    for mk, ticker, _name, _w, n in holdings:
        pays = series([(f"2026-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}", 1.0)
                       for i in range(n)]) if n else None
        spec = {"currency": "USD" if mk == "US" else "KRW", "latest": 100.0,
                "distributions": pays}
        (us if mk == "US" else kr)[ticker] = spec
    market.set_us(us)
    market.set_kr(kr)
    p = Portfolio(name="t", initial_capital_krw=100_000_000, max_squad_size=26)
    for mk, ticker, name, w, _n in holdings:
        p.add(Security(market=mk, ticker=ticker, display_name=name,
                       currency="USD" if mk == "US" else "KRW", target_weight=w))
    return portfolio_service.compute(p)


def test_bars_add_up_to_one_hundred(market):
    comp = _comp(market, [("US", "SCHD", "", 0.3, 4), ("KR", "458730", "TIGER 미국배당다우존스", 0.2, 12)])
    for bar in cs.bars(comp):
        assert sum(s.pct for s in bar.slices) == pytest.approx(100.0), bar.title


def test_bars_are_the_three_we_promised(market):
    comp = _comp(market, [("US", "SCHD", "", 0.5, 4)])
    assert [b.title for b in cs.bars(comp)] == ["어느 나라", "어떤 종류", "언제 들어오나"]


def test_no_holdings_no_bars(market):
    market.set_fx(rate=1_000.0)
    assert cs.bars(portfolio_service.compute(Portfolio(name="t"))) == []


def test_country_split_is_by_money_not_by_count(market):
    """종목 수가 아니라 담은 돈으로 나눠야 합니다."""
    comp = _comp(market, [("US", "SCHD", "", 0.6, 4),
                          ("KR", "458730", "TIGER 미국배당다우존스", 0.2, 12),
                          ("KR", "329200", "TIGER 리츠부동산인프라", 0.2, 12)])
    country = next(b for b in cs.bars(comp) if b.title == "어느 나라")
    got = {s.label: s.pct for s in country.slices}
    assert got["미국"] == pytest.approx(60.0, abs=0.5)
    assert got["한국"] == pytest.approx(40.0, abs=0.5)


def test_quarterly_only_portfolio_is_visible_in_the_schedule_bar(market):
    """분기배당만 담으면 세 달 중 두 달은 0원인데, 대부분 짜고 나서야 압니다."""
    comp = _comp(market, [("US", "SCHD", "", 0.5, 4), ("US", "VYM", "", 0.5, 4)])
    schedule = next(b for b in cs.bars(comp) if b.title == "언제 들어오나")
    assert [s.label for s in schedule.slices] == [cs.SCHEDULE_QUARTERLY]


# =====================================================================
# 성향 라벨
# =====================================================================
def test_covered_call_heavy_reads_as_aggressive(market):
    comp = _comp(market, [("US", "JEPQ", "", 0.4, 12), ("US", "QYLD", "", 0.4, 12),
                          ("US", "SCHD", "", 0.2, 4)])
    label, why = cs.tilt(comp)
    assert "공격형" in label
    assert "커버드콜" in why and "%" in why


def test_plain_dividends_read_as_stable(market):
    comp = _comp(market, [("US", "SCHD", "", 0.5, 4), ("US", "TLT", "", 0.5, 12)])
    label, _ = cs.tilt(comp)
    assert "안정형" in label


def test_a_mix_reads_as_balanced(market):
    comp = _comp(market, [("US", "JEPQ", "", 0.3, 12), ("US", "SCHD", "", 0.7, 4)])
    label, _ = cs.tilt(comp)
    assert "보통형" in label


def test_the_label_never_tells_you_what_to_do(market):
    """평가가 아니라 거울입니다. 지시하는 말이 들어가면 그건 추천입니다."""
    comp = _comp(market, [("US", "JEPQ", "", 1.0, 12)])
    label, why = cs.tilt(comp)
    text = label + why
    for banned in ("빼", "담으세요", "추천", "좋", "나쁘", "위험하니"):
        assert banned not in text, f"'{banned}' 는 쓰면 안 됩니다: {text}"
    assert "가깝습니다" in label


def test_no_tilt_without_holdings(market):
    market.set_fx(rate=1_000.0)
    assert cs.tilt(portfolio_service.compute(Portfolio(name="t"))) is None


def test_the_screen_shows_the_bars_and_the_tilt(market):
    comp_holdings = [("US", "JEPQ", "", 0.6, 12), ("US", "SCHD", "", 0.4, 4)]
    _comp(market, comp_holdings)      # 시장 데이터만 설치
    p = Portfolio(name="t", initial_capital_krw=100_000_000)
    p.add(Security(market="US", ticker="JEPQ", currency="USD", target_weight=0.6))
    p.add(Security(market="US", ticker="SCHD", currency="USD", target_weight=0.4))
    at = AppTest.from_file(APP_PATH, default_timeout=90)
    at.session_state["portfolio"] = p
    at.run()
    assert not at.exception
    body = " ".join(m.value for m in at.markdown)
    assert "어느 나라" in body and "어떤 종류" in body and "언제 들어오나" in body
    assert "지금 구성은" in body and "가깝습니다" in body


# =====================================================================
# 최대낙폭 -- 수익만 보여주지 않기
# =====================================================================
def _crash_history():
    """올랐다가 반토막 났다가 회복하는 길. 시작과 끝만 보면 +20% 입니다."""
    return series([("2021-01-04", 100.0), ("2022-01-04", 200.0),
                   ("2023-01-04", 100.0), ("2024-01-04", 150.0),
                   ("2026-09-10", 120.0)])


def test_backtest_reports_the_drawdown_the_two_endpoints_hide(market):
    """시작과 끝만 보면 +20% 인데, 도중에 -50% 를 지나왔습니다."""
    market.set_fx(rate=1_000.0)
    market.set_kr({"A": {"currency": "KRW", "history": _crash_history()}})
    p = Portfolio(name="bt", initial_capital_krw=10_000_000)
    p.add(Security(market="KR", ticker="A", currency="KRW", target_weight=1.0))

    r = backtest_service.run_backtest(p, date(2021, 1, 4), initial_capital_krw=10_000_000)
    assert r.ok, r.message
    assert r.return_pct > 0                       # 끝만 보면 이득인데
    assert r.max_drawdown_pct == pytest.approx(-50.0, abs=1.0)   # 도중에 반토막
    assert r.max_drawdown_date == date(2023, 1, 4)


def test_a_line_that_only_goes_up_has_no_drawdown(market):
    market.set_fx(rate=1_000.0)
    market.set_kr({"A": {"currency": "KRW",
                         "history": series([("2021-01-04", 100.0), ("2026-09-10", 200.0)])}})
    p = Portfolio(name="bt", initial_capital_krw=10_000_000)
    p.add(Security(market="KR", ticker="A", currency="KRW", target_weight=1.0))
    r = backtest_service.run_backtest(p, date(2021, 1, 4), initial_capital_krw=10_000_000)
    assert r.ok and r.max_drawdown_pct == 0.0


def test_cash_softens_the_drawdown_but_not_by_half(market):
    """남긴 현금은 안 떨어지니 낙폭을 줄여줍니다. 다만 "절반" 은 아닙니다.

    낙폭은 **시작점이 아니라 고점** 에서 잽니다. 시드 1,000만 중 500만만 담고
    그 종목이 2배가 되면 고점의 전체 자산은 1,500만(주식 1,000만 + 현금 500만)
    입니다. 거기서 주식이 반토막나면 1,000만이 되므로 -33% 이지 -25% 가 아닙니다.
    직관과 어긋나는 지점이라 테스트로 적어둡니다.
    """
    market.set_fx(rate=1_000.0)
    market.set_kr({"A": {"currency": "KRW", "history": _crash_history()}})
    p = Portfolio(name="bt", initial_capital_krw=10_000_000)
    p.add(Security(market="KR", ticker="A", currency="KRW", target_weight=0.5))
    r = backtest_service.run_backtest(p, date(2021, 1, 4), initial_capital_krw=10_000_000)
    assert r.ok
    # 전부 담았을 때(-50%)보다는 얕지만, 절반(-25%)보다는 깊습니다.
    assert r.max_drawdown_pct == pytest.approx(-33.3, abs=1.0)


def test_the_screen_puts_the_drawdown_next_to_the_gain(market):
    """수익만 크게 쓰면 앱이 아니라 광고가 됩니다."""
    market.set_fx(rate=1_000.0)
    market.set_kr({"A": {"currency": "KRW", "history": _crash_history(), "latest": 120.0}})
    p = Portfolio(name="bt", initial_capital_krw=10_000_000)
    p.add(Security(market="KR", ticker="A", currency="KRW", target_weight=1.0))

    at = AppTest.from_file(APP_PATH, default_timeout=90)
    at.session_state["portfolio"] = p
    at.run()
    [d for d in at.date_input if d.label == "시작일"][0].set_value(date(2021, 1, 4)).run()
    [b for b in at.button if b.label == "실행하기"][0].click().run()
    assert not at.exception

    notes = [m.value for m in at.markdown if m.value.startswith("<div class='note'>")]
    summary = [n for n in notes if "이 구성이었다면" in n]
    assert summary, f"한 문장 요약이 없습니다: {notes}"
    assert "빠진 구간이 있었습니다" in summary[0]
    assert "-50" in summary[0] or "-49" in summary[0]
