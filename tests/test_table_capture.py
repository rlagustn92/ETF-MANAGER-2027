"""표를 그림으로 복사·저장하기 (비교표 · 분배금 달력 · 백테스트).

여기서 지키는 것
----------------
**그림은 앱 밖으로 퍼집니다.** 앞뒤 맥락이 없는 곳에서 혼자 읽히므로,
화면에서 지키던 규칙을 그림에서도 똑같이 지켜야 합니다.

1. 초록(=많을수록 원하던 것)은 화면과 **같은 줄에만**.
2. 백테스트 그림에는 **최대낙폭이 반드시** 들어갑니다. 수익만 담긴 그림은
   계산 결과가 아니라 광고입니다.
3. 달력 그림에는 "예상" / "지금 이 구성이었다면" 이 그대로 붙습니다.
"""

from __future__ import annotations

import pathlib
from datetime import date

import pytest

import config
from models.portfolio import Portfolio
from models.security import Security
from services import backtest_service, calendar_service, compare_service
from services import portfolio_service
from tests.conftest import series

CAPTURE_HTML = (pathlib.Path(__file__).resolve().parent.parent
                / "components" / "table_capture" / "frontend" / "index.html")
TODAY = date(2026, 9, 16)


def _cells(row) -> list[str]:
    return [c.get("t", "") for c in row["cells"]]


# =====================================================================
# 비교표
# =====================================================================
def _two_comps(market):
    market.set_fx(rate=1_000.0)
    pays = series([(f"2026-{m:02d}-15", 1.0) for m in range(1, 10)])
    market.set_us({"SCHD": {"currency": "USD", "latest": 100.0, "distributions": pays},
                   "JEPQ": {"currency": "USD", "latest": 100.0, "distributions": pays}})
    a = Portfolio(name="현재안", initial_capital_krw=100_000_000)
    a.add(Security(market="US", ticker="SCHD", currency="USD", target_weight=0.3))
    b = Portfolio(name="공격안", initial_capital_krw=100_000_000)
    b.add(Security(market="US", ticker="JEPQ", currency="USD", target_weight=0.6))
    return portfolio_service.compute(a), portfolio_service.compute(b)


def test_compare_capture_has_every_row(market):
    a, b = _two_comps(market)
    rows = compare_service.capture_rows(a, b)
    labels = [_cells(r)[0] for r in rows]
    assert labels == [r.label for r in compare_service.rows(a, b)]


def test_compare_capture_marks_the_same_side_as_the_screen(market):
    a, b = _two_comps(market)
    for screen, shot in zip(compare_service.rows(a, b),
                            compare_service.capture_rows(a, b)):
        marked = [i for i, c in enumerate(shot["cells"]) if c.get("win")]
        if screen.winner is None:
            assert marked == [], f"{screen.label}: 화면에선 안 칠하는데 그림에선 칠했습니다"
        else:
            assert marked == [1 if screen.winner == "a" else 2], screen.label


def test_compare_capture_only_bars_comparable_rows(market):
    a, b = _two_comps(market)
    for screen, shot in zip(compare_service.rows(a, b),
                            compare_service.capture_rows(a, b)):
        has_bar = any("bar" in c for c in shot["cells"])
        assert has_bar == (screen.bars is not None), screen.label


def test_compare_capture_separates_the_two_kinds_of_rows(market):
    a, b = _two_comps(market)
    rows = compare_service.capture_rows(a, b)
    seps = [i for i, r in enumerate(rows) if r.get("sep")]
    assert len(seps) == 1, "'많을수록 원하던 것' 과 사실 줄 사이에 선이 하나 있어야 합니다"
    assert _cells(rows[seps[0]])[0] == "투자금 대비 분배율"


# =====================================================================
# 분배금 달력
# =====================================================================
@pytest.fixture
def cal_comp(market):
    market.set_fx(rate=1_000.0)
    pays = series([(f"2026-{m:02d}-18", 0.5) for m in range(1, 10)]
                  + [(f"2025-{m:02d}-18", 0.5) for m in range(10, 13)])
    market.set_us({"MON": {"currency": "USD", "latest": 100.0, "distributions": pays}})
    p = Portfolio(name="t", initial_capital_krw=10_000_000)
    p.add(Security(market="US", ticker="MON", display_name="Monthly", currency="USD",
                   target_weight=0.5))
    return portfolio_service.compute(p)


def test_calendar_capture_ends_with_a_total(cal_comp):
    """그림만 보는 사람은 앱의 큰 숫자를 못 봅니다."""
    plan = calendar_service.month_plan(cal_comp, 2026, 7, today=TODAY)
    rows = calendar_service.capture_rows(plan)
    assert _cells(rows[-1])[0] == "합계"
    assert rows[-2].get("sep") is True


def test_calendar_capture_of_an_empty_month_still_has_a_total(cal_comp):
    plan = calendar_service.month_plan(cal_comp, 2026, 7, today=TODAY)
    plan.entries = []
    rows = calendar_service.capture_rows(plan)
    assert len(rows) == 1 and _cells(rows[0])[0] == "합계"


def test_calendar_capture_notes_say_forecast_for_future_months(cal_comp):
    plan = calendar_service.month_plan(cal_comp, 2026, 11, today=TODAY)
    notes = " ".join(calendar_service.capture_notes(plan))
    assert "예상" in notes


def test_calendar_capture_notes_keep_the_honest_wording_for_past_months(cal_comp):
    """그림은 맥락 없이 퍼집니다. '받으셨습니다' 로 읽히면 안 됩니다."""
    plan = calendar_service.month_plan(cal_comp, 2026, 7, today=TODAY)
    notes = " ".join(calendar_service.capture_notes(plan))
    assert "지금 이 구성이었다면" in notes


def test_calendar_capture_lists_the_silent_securities(cal_comp):
    plan = calendar_service.month_plan(cal_comp, 2026, 7, today=TODAY)
    plan.silent = ["TLT", "O"]
    assert any("지급 없음" in n for n in calendar_service.capture_notes(plan))


# =====================================================================
# 백테스트
# =====================================================================
def _backtest(market, history, *, dists=None, include=False):
    market.set_fx(rate=1_000.0)
    entry = {"currency": "KRW", "history": history, "latest": 120.0}
    if dists is not None:
        entry["distributions"] = dists
    market.set_kr({"A": entry})
    p = Portfolio(name="bt", initial_capital_krw=10_000_000)
    p.add(Security(market="KR", ticker="A", currency="KRW", target_weight=1.0))
    return backtest_service.run_backtest(p, date(2021, 1, 4),
                                         initial_capital_krw=10_000_000,
                                         include_distributions=include)


def test_backtest_capture_always_shows_the_drawdown(market):
    """수익만 담긴 그림은 계산 결과가 아니라 광고입니다."""
    r = _backtest(market, series([("2021-01-04", 100.0), ("2022-01-04", 200.0),
                                  ("2023-01-04", 100.0), ("2026-09-10", 150.0)]))
    assert r.ok
    labels = [_cells(row)[0] for row in backtest_service.capture_rows(r)]
    assert "도중 최대낙폭" in labels
    values = {_cells(row)[0]: _cells(row)[1] for row in backtest_service.capture_rows(r)}
    assert "-50" in values["도중 최대낙폭"] or "-49" in values["도중 최대낙폭"]


def test_backtest_capture_says_so_when_it_could_not_measure_the_drawdown(market):
    """낙폭 줄을 아예 빼버리면 '낙폭이 없었다' 로 읽힙니다."""
    r = _backtest(market, series([("2021-01-04", 100.0), ("2026-09-10", 200.0)]))
    values = {_cells(row)[0]: _cells(row)[1] for row in backtest_service.capture_rows(r)}
    assert values["도중 최대낙폭"] == "계산 못 함"


def test_backtest_capture_marks_a_gain_but_never_the_drawdown(market):
    r = _backtest(market, series([("2021-01-04", 100.0), ("2022-01-04", 200.0),
                                  ("2023-01-04", 100.0), ("2026-09-10", 150.0)]))
    for row in backtest_service.capture_rows(r):
        if _cells(row)[0] == "도중 최대낙폭":
            assert not row["cells"][1].get("win")


def test_backtest_capture_has_the_period(market):
    r = _backtest(market, series([("2021-01-04", 100.0), ("2026-09-10", 200.0)]))
    values = {_cells(row)[0]: _cells(row)[1] for row in backtest_service.capture_rows(r)}
    assert "~" in values["기간"] and "년" in values["기간"]


def test_backtest_capture_carries_the_whole_screen(market):
    """요약만 담은 그림은 '무엇을 담아서 그렇게 됐는지' 가 빠진 결과 자랑입니다."""
    r = _backtest(market, series([("2021-01-04", 100.0), ("2026-09-10", 200.0)]))
    sections = backtest_service.capture_sections(r)
    assert len(sections) == 2, "요약 + 종목별 두 덩어리여야 합니다"
    assert [_cells(x)[0] for x in sections[0]["rows"]] == \
           [_cells(x)[0] for x in backtest_service.capture_rows(r)]
    assert [_cells(x)[0] for x in sections[1]["rows"]] == ["A"]


def test_backtest_capture_holdings_columns_match_the_screen(market):
    """화면 표와 칸이 다르면 '내가 보던 그 표' 가 아니게 됩니다."""
    screen = ["종목", "살(BUY) 비율", "매수가", "살 때 환율", "수량",
              "살 때 원금(₩)", "구간내 분할", "종료가", "평가금액(₩)", "지금 환율"]
    r = _backtest(market, series([("2021-01-04", 100.0), ("2026-09-10", 200.0)]))
    holdings = backtest_service.capture_holdings(r)
    assert holdings["columns"] == screen
    for row in holdings["rows"]:
        assert len(row["cells"]) == len(screen)


def test_backtest_capture_shows_how_much_actually_went_in(market):
    """시드 전부가 종목에 들어가는 일은 드뭅니다. 현금이 얼마 남았는지가 빠지면
    '1억이 2억' 만 남습니다."""
    r = _backtest(market, series([("2021-01-04", 100.0), ("2026-09-10", 200.0)]))
    labels = [_cells(row)[0] for row in backtest_service.capture_rows(r)]
    assert any("총 원금" in x for x in labels)
    assert any("잔여현금" in x for x in labels), labels


def _with_dividends(market):
    return _backtest(
        market,
        series([("2021-01-04", 100.0), ("2022-01-04", 200.0),
                ("2023-01-04", 100.0), ("2026-09-10", 150.0)]),
        dists=series([(f"{y}-{m:02d}-15", 2.0)
                      for y in range(2021, 2027) for m in (3, 6, 9, 12)]),
        include=True)


def _value(rows, label):
    return {_cells(x)[0]: _cells(x)[1] for x in rows}[label]


def test_backtest_capture_breaks_the_total_into_its_parts(market):
    """한 칸에 주식·현금·분배금을 뭉쳐 놓으면 얼마가 주가로 번 것인지 알 수 없습니다."""
    r = _with_dividends(market)
    assert r.ok and r.distributions_cash_krw > 0
    rows = backtest_service.capture_rows(r)
    labels = [_cells(x)[0] for x in rows]
    assert "최종 자산 (합계)" in labels, labels
    for part in ("└ 주식 평가액", "└ 잔여현금", "└ 받은 분배금 (세전)"):
        assert part in labels, labels
    # 쪼갠 것들은 합계 **바로 아래** 붙어 있어야 쪼갠 것으로 읽힙니다.
    i = labels.index("최종 자산 (합계)")
    assert labels[i + 1:i + 4] == ["└ 주식 평가액", "└ 잔여현금", "└ 받은 분배금 (세전)"]


def test_the_parts_add_up_to_the_total(market):
    """쪼갠 값이 합계와 안 맞으면 쪼갠 의미가 없습니다. 원본 숫자로 확인합니다."""
    for r in (_with_dividends(market),
              _backtest(market, series([("2021-01-04", 100.0), ("2026-09-10", 200.0)]))):
        parts = r.holdings_value_krw + r.cash_balance_krw + (
            r.distributions_cash_krw if r.include_distributions else 0.0)
        assert parts == pytest.approx(r.final_value_krw, abs=1e-6)


def test_backtest_capture_does_not_claim_dividends_when_they_are_off(market):
    r = _backtest(market, series([("2021-01-04", 100.0), ("2026-09-10", 200.0)]))
    labels = [_cells(row)[0] for row in backtest_service.capture_rows(r)]
    assert "최종 자산 (합계)" in labels
    assert not any("분배금" in x for x in labels), labels


def test_backtest_capture_notes_say_the_drawdown_excludes_the_dividend_cash(market):
    """한 그림 안에 기준이 다른 두 숫자(최종 자산 · 최대낙폭)가 나란히 있습니다."""
    r = _with_dividends(market)
    notes = " ".join(backtest_service.capture_notes(r))
    assert "재투자하지" in notes and "빼고 잰" in notes


def test_backtest_capture_notes_always_carry_the_disclaimer(market):
    for r in (_with_dividends(market),
              _backtest(market, series([("2021-01-04", 100.0), ("2026-09-10", 200.0)]))):
        notes = " ".join(backtest_service.capture_notes(r))
        assert config.BACKTEST_DISCLAIMER in notes
        assert "보장하지 않습니다" in notes


def test_backtest_capture_of_a_failed_run_has_no_holdings_section(market):
    """실패한 결과에 빈 표를 붙이면 '담은 게 없다' 로 읽힙니다."""
    r = backtest_service.BacktestResult(ok=False, message="실패")
    sections = backtest_service.capture_sections(r)
    assert len(sections) == 1


# =====================================================================
# 파일 이름
# =====================================================================
def test_each_kind_gets_its_own_filename():
    """한 전술에서 셋을 다 받으면 이름이 겹쳐 "(1)" 이 붙습니다."""
    names = {config.table_image_filename(k, "월배당 공격형")
             for k in ("비교", "분배금달력_202609", "백테스트")}
    assert len(names) == 3
    for n in names:
        assert n.endswith(".png")
        assert "월배당_공격형" in n
        assert f"{config.today_local():%Y%m%d}" in n


def test_filename_survives_a_hostile_tactic_name():
    out = config.table_image_filename("비교", '나쁜/이름:테스트*?')
    assert "/" not in out and "\\" not in out and ":" not in out


# =====================================================================
# 컴포넌트
# =====================================================================
def test_the_component_draws_instead_of_screenshotting():
    """화면을 찍는 방식은 외부 라이브러리에 묶이고 Streamlit 구조가 바뀌면 깨집니다.

    (주석에는 html2canvas 가 '왜 안 쓰는지' 로 나오므로, 단어가 아니라
     **실제로 스크립트를 불러오는지** 를 봅니다)
    """
    html = CAPTURE_HTML.read_text(encoding="utf-8")
    assert "<script src=" not in html, "외부 스크립트를 불러오고 있습니다"
    assert "window.parent.document" not in html, "부모 문서를 들여다보고 있습니다"
    assert "getContext" in html and "toBlob" in html


def test_the_component_takes_more_than_one_table():
    """백테스트 그림은 '요약 + 종목별' 두 덩어리입니다. 컴포넌트가 하나만 받으면
    파이썬 쪽에서 아무리 두 덩어리를 만들어도 그림에는 안 들어갑니다."""
    html = CAPTURE_HTML.read_text(encoding="utf-8")
    assert "args.sections" in html
    assert "args.rows" not in html and "args.columns" not in html


def test_the_component_uses_the_same_font_list_as_the_pitch():
    """같은 앱에서 나온 두 그림의 글자 모양이 달라 보이면 안 됩니다."""
    html = CAPTURE_HTML.read_text(encoding="utf-8")
    pitch = (pathlib.Path(__file__).resolve().parent.parent / "components"
             / "football_pitch" / "frontend" / "index.html").read_text(encoding="utf-8")
    for face in ('"Segoe UI"', '"Noto Sans KR"', '"Malgun Gothic"'):
        assert face in html and face in pitch


def test_the_component_falls_back_when_the_clipboard_is_blocked():
    html = CAPTURE_HTML.read_text(encoding="utf-8")
    assert "clipboard.write" in html
    assert "window.open" in html, "클립보드가 막힌 브라우저에서 빠져나갈 길이 없습니다"
