"""두 전술 나란히 비교 테스트.

여기서 지키는 것
----------------
1. **색으로 추천하지 않는다.** 분배금·분배율은 많을수록 사용자가 원한 것이니 칠해도
   되지만, 커버드콜 비중이나 종목 수는 많다고 좋은 게 아닙니다. 그런 줄까지 칠하면
   색이 곧 추천이 됩니다.
2. **창을 열 때만 계산한다.** 첫 화면에서 B 전술까지 계산하면 평소 속도가 느려집니다.
3. **닫으면 닫힌 채로 있는다.** 드롭다운을 되돌려놓지 않으면 곧바로 다시 열립니다.
"""

from __future__ import annotations

import pathlib

import pytest
from streamlit.testing.v1 import AppTest

from models.portfolio import Portfolio
from models.security import Security
from services import compare_service, portfolio_service, slot_service
from tests.conftest import series

APP_PATH = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")


def _pays(n: int):
    return series([(f"2026-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}", 1.0) for i in range(n)])


def _install(market, specs):
    """specs: [(market, ticker, name, n_payments)]"""
    market.set_fx(rate=1_000.0)
    us, kr = {}, {}
    for mk, ticker, _name, n in specs:
        entry = {"currency": "USD" if mk == "US" else "KRW", "latest": 100.0,
                 "distributions": _pays(n) if n else None}
        (us if mk == "US" else kr)[ticker] = entry
    market.set_us(us)
    market.set_kr(kr)


def _portfolio(specs, weights, capital=100_000_000) -> Portfolio:
    p = Portfolio(name="t", initial_capital_krw=capital)
    for (mk, ticker, name, _n), w in zip(specs, weights):
        p.add(Security(market=mk, ticker=ticker, display_name=name,
                       currency="USD" if mk == "US" else "KRW", target_weight=w))
    return p


# =====================================================================
# 어느 줄을 칠해도 되는가
# =====================================================================
def test_more_income_is_marked_as_the_better_side():
    row = compare_service.CompareRow("월 분배금", "50만", "80만", True, 500_000, 800_000)
    assert row.winner == "b"


def test_a_tie_is_not_marked():
    row = compare_service.CompareRow("월 분배금", "50만", "50만", True, 500_000, 500_000)
    assert row.winner is None


def test_rows_that_are_not_about_what_you_asked_for_are_never_marked():
    """커버드콜 비중이 높은 쪽을 초록으로 칠하면 그건 '이걸 담으세요' 가 됩니다."""
    row = compare_service.CompareRow("커버드콜 비중", "0%", "68%", False, 0.0, 68.0)
    assert row.winner is None


def test_only_income_rows_can_be_coloured(market):
    _install(market, [("US", "SCHD", "", 4), ("US", "JEPQ", "", 12)])
    a = portfolio_service.compute(_portfolio([("US", "SCHD", "", 4)], [0.5]))
    b = portfolio_service.compute(_portfolio([("US", "JEPQ", "", 12)], [0.5]))

    colourable = {r.label for r in compare_service.rows(a, b)
                  if r.higher_is_what_you_asked_for}
    assert colourable == {"월 분배금", "연 분배금", "투자금 대비 분배율"}

    for row in compare_service.rows(a, b):
        if row.label in ("커버드콜 비중", "종목 수", "총 원금", "남은 현금"):
            assert row.winner is None, f"{row.label} 은 칠하면 안 됩니다"


def test_the_table_has_the_rows_we_promised(market):
    _install(market, [("US", "SCHD", "", 4)])
    a = b = portfolio_service.compute(_portfolio([("US", "SCHD", "", 4)], [0.5]))
    labels = [r.label for r in compare_service.rows(a, b)]
    assert labels == ["월 분배금", "연 분배금", "투자금 대비 분배율", "종목 수",
                      "커버드콜 비중", "총 원금", "남은 현금"]


# =====================================================================
# 겹치는 종목
# =====================================================================
def test_overlap_lists_what_both_portfolios_hold(market):
    specs = [("US", "SCHD", "", 4), ("US", "JEPQ", "", 12),
             ("KR", "458730", "TIGER 미국배당다우존스", 12)]
    _install(market, specs)
    a = portfolio_service.compute(_portfolio(specs[:2], [0.5, 0.5]))
    b = portfolio_service.compute(_portfolio(specs[1:], [0.5, 0.5]))
    assert compare_service.overlap(a, b) == ["JEPQ"]


def test_overlap_uses_the_korean_name_not_the_code(market):
    specs = [("KR", "458730", "TIGER 미국배당다우존스", 12)]
    _install(market, specs)
    a = portfolio_service.compute(_portfolio(specs, [0.5]))
    assert compare_service.overlap(a, a) == ["TIGER 미국배당다우존스"]


def test_no_overlap_is_an_empty_list(market):
    _install(market, [("US", "SCHD", "", 4), ("US", "JEPQ", "", 12)])
    a = portfolio_service.compute(_portfolio([("US", "SCHD", "", 4)], [0.5]))
    b = portfolio_service.compute(_portfolio([("US", "JEPQ", "", 12)], [0.5]))
    assert compare_service.overlap(a, b) == []


# =====================================================================
# 목표와 이어지기
# =====================================================================
def test_goal_line_shows_both_sides(market):
    _install(market, [("US", "SCHD", "", 4), ("US", "JEPQ", "", 12)])
    a = portfolio_service.compute(_portfolio([("US", "SCHD", "", 4)], [0.5]))
    b = portfolio_service.compute(_portfolio([("US", "JEPQ", "", 12)], [0.5]))
    line = compare_service.goal_progress_line(a, b, 1_000_000)
    assert "→" in line and "목표" in line


def test_no_goal_no_line(market):
    _install(market, [("US", "SCHD", "", 4)])
    a = portfolio_service.compute(_portfolio([("US", "SCHD", "", 4)], [0.5]))
    assert compare_service.goal_progress_line(a, a, 0) == ""
    assert compare_service.goal_progress_line(a, a, -1) == ""


# =====================================================================
# 화면
# =====================================================================
def _two_slots(at, market):
    specs = [("US", "SCHD", "", 4), ("US", "JEPQ", "", 12)]
    _install(market, specs)
    a = _portfolio([specs[0]], [0.5])
    a.name = "현재안"
    b = _portfolio([specs[1]], [0.5])
    b.name = "공격안"
    at.session_state["portfolio"] = a
    at.session_state["slots"] = [slot_service.slot_from_portfolio(a),
                                 slot_service.slot_from_portfolio(b)]
    at.session_state["slot_active"] = 0
    return at


def _cmp_buttons(at):
    return [b for b in at.button if b.key and b.key.startswith("cmp_")
            and b.key != "cmp_close"]


def test_no_compare_control_with_only_one_slot(market):
    _install(market, [("US", "SCHD", "", 4)])
    at = AppTest.from_file(APP_PATH, default_timeout=90)
    at.session_state["portfolio"] = _portfolio([("US", "SCHD", "", 4)], [0.5])
    at.run()
    assert not _cmp_buttons(at)


def test_the_button_names_the_tactic_it_compares_with(market):
    """드롭다운은 열어서 골라야 하고 뭔지 모르고 지나칩니다. 버튼은 글자가 그대로 보입니다."""
    at = _two_slots(AppTest.from_file(APP_PATH, default_timeout=90), market)
    at.run()
    assert not at.exception
    labels = [b.label for b in _cmp_buttons(at)]
    assert labels == ["⇄ 공격안 비교"]


def test_button_label_has_no_wrong_particle():
    """"○○ 과 비교" 는 받침 없는 이름에 틀립니다("예시 와" 가 맞음).
    조사를 맞추는 것보다 아예 빼는 쪽이 안전합니다."""
    got = compare_service.button_label("공격배당형 예시")
    assert got == "⇄ 공격배당형 예시 비교"
    assert " 과 " not in got and " 와 " not in got


def test_button_label_shortens_a_long_name():
    got = compare_service.button_label("아주아주아주긴전술이름입니다")
    assert got.startswith("⇄ ") and got.endswith(" 비교")
    assert "…" in got
    assert len(got) <= compare_service.BUTTON_NAME_MAX + 6


def test_bars_show_how_many_times_bigger():
    """"124만" 과 "41.7만" 을 나란히 놔도 몇 배인지는 한 번 계산해야 압니다."""
    row = compare_service.CompareRow("월 분배금", "124만", "41.7만", True,
                                     1_240_000, 417_000)
    a, b = row.bars
    assert a == pytest.approx(100.0)
    assert b == pytest.approx(417_000 / 1_240_000 * 100.0)


def test_no_bars_on_rows_that_are_not_about_what_you_asked_for():
    """막대도 크기 비교라서, 많다고 좋은 게 아닌 줄에 그리면 추천이 됩니다."""
    assert compare_service.CompareRow("커버드콜 비중", "0%", "68%", False,
                                      0.0, 68.0).bars is None


def test_no_bars_when_a_value_is_negative():
    """잔여현금이 음수면 길이 비유가 깨집니다."""
    assert compare_service.CompareRow("남은 현금", "-5만", "3만", True,
                                      -50_000, 30_000).bars is None


def test_no_bars_when_both_are_zero():
    assert compare_service.CompareRow("월 분배금", "0원", "0원", True, 0, 0).bars is None


def test_bars_survive_a_zero_on_one_side():
    row = compare_service.CompareRow("월 분배금", "50만", "0원", True, 500_000, 0)
    assert row.bars == (100.0, 0.0)


def test_button_label_of_an_empty_name():
    assert compare_service.button_label("") == "⇄ 전술 비교"
    assert compare_service.button_label("   ") == "⇄ 전술 비교"


def test_the_table_head_uses_the_tactic_names(market):
    """"지금 / 저쪽" 은 한 번 더 머릿속에서 옮겨야 해서 헷갈립니다."""
    at = _two_slots(AppTest.from_file(APP_PATH, default_timeout=90), market)
    at.run()
    _cmp_buttons(at)[0].click().run()
    assert not at.exception

    table = [m.value for m in at.markdown if "table class='cmp'" in m.value]
    assert table, "비교 표가 없습니다"
    assert "현재안" in table[0] and "공격안" in table[0]
    assert ">저쪽<" not in table[0]


def test_the_table_draws_bars_only_on_comparable_rows(market):
    at = _two_slots(AppTest.from_file(APP_PATH, default_timeout=90), market)
    at.run()
    _cmp_buttons(at)[0].click().run()
    html = [m.value for m in at.markdown if "table class='cmp'" in m.value][0]
    rows = html.split("<tr")
    for chunk in rows:
        if "커버드콜 비중" in chunk or "종목 수" in chunk:
            assert "class='b'" not in chunk, "많다고 좋은 게 아닌 줄에 막대가 있습니다"
    assert "class='b'" in html, "분배금 줄에 막대가 없습니다"


def test_nothing_is_computed_until_you_pick(market):
    """첫 화면에서 B 전술까지 계산하면 평소 속도가 느려집니다."""
    at = _two_slots(AppTest.from_file(APP_PATH, default_timeout=90), market)
    at.run()
    assert "cmp_open" not in at.session_state or at.session_state["cmp_open"] is False


def test_pressing_the_button_opens_the_comparison(market):
    at = _two_slots(AppTest.from_file(APP_PATH, default_timeout=90), market)
    at.run()
    _cmp_buttons(at)[0].click().run()
    assert not at.exception
    assert at.session_state["cmp_open"] is True
    assert at.session_state["cmp_target"] == 1


def test_closing_stays_closed(market):
    """버튼으로 열기 때문에 닫으면 그냥 닫힌 채로 있어야 합니다.
    (드롭다운이던 시절엔 고른 값이 남아서 닫자마자 다시 열렸습니다)"""
    at = _two_slots(AppTest.from_file(APP_PATH, default_timeout=90), market)
    at.run()
    _cmp_buttons(at)[0].click().run()

    [b for b in at.button if b.key == "cmp_close"][0].click().run()
    assert not at.exception
    assert at.session_state["cmp_open"] is False

    at.run()      # 한 번 더 그려도 다시 열리면 안 됩니다
    assert at.session_state["cmp_open"] is False


def test_comparison_survives_a_slot_that_went_away(market):
    """비교 대상이 사라진 뒤에 창이 열리면 앱이 죽으면 안 됩니다."""
    at = _two_slots(AppTest.from_file(APP_PATH, default_timeout=90), market)
    at.run()
    at.session_state["cmp_open"] = True
    at.session_state["cmp_target"] = 99        # 없는 칸
    at.run()
    assert not at.exception
    assert at.session_state["cmp_open"] is False
