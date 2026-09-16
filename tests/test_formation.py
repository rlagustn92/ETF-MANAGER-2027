"""포메이션 · 주장 완장 · 이름 추천 테스트.

여기서 지키는 것
----------------
1. **절대 자동으로 옮기지 않는다.** 사용자가 손으로 맞춰둔 배치를 앱이 말없이
   흐트러뜨리면 화가 납니다. 버튼을 눌렀을 때만 움직입니다.
2. **자리에 뜻이 있다.** 커버드콜은 공격, 채권은 수비. 그래야 전술판을 보는 것만으로
   "공격에 몰빵했구나" 가 보입니다.
3. **0 을 숨기지 않는다.** "0-0-5" 는 전부 공격에 있다는 뜻이고, 그게 이 표기의 쓸모입니다.
"""

from __future__ import annotations

import pathlib

import pytest
from streamlit.testing.v1 import AppTest

import pitch_grid
from models.portfolio import Portfolio
from models.security import Security
from services import composition_service as cs
from services import formation_service as fs
from services import portfolio_service
from tests.conftest import series

APP_PATH = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")


def _p(specs, capital=100_000_000) -> Portfolio:
    """specs: [(market, ticker, name, weight)]"""
    p = Portfolio(name="t", initial_capital_krw=capital, max_squad_size=26)
    for mk, ticker, name, w in specs:
        p.add(Security(market=mk, ticker=ticker, display_name=name,
                       currency="USD" if mk == "US" else "KRW", target_weight=w))
    return p


def _row(portfolio, ticker) -> str:
    sec = next(s for s in portfolio.securities if s.ticker == ticker)
    return pitch_grid.split(sec.slot)[0]


# =====================================================================
# 자리에 뜻 주기
# =====================================================================
@pytest.mark.parametrize("ticker,name,expected_row", [
    ("JEPQ", "", "ST"),                       # 커버드콜 -> 공격
    ("O", "", "AM"),                          # 리츠 -> 공격형 미드
    ("SCHD", "", "MC"),                       # 배당주 -> 중앙
    ("TLT", "", "DF"),                        # 채권 -> 수비
    ("ZZZZ", "", "DM"),                       # 모르는 것 -> 중앙 뒤
])
def test_each_kind_has_a_line(ticker, name, expected_row):
    sec = Security(market="US", ticker=ticker, display_name=name, currency="USD")
    assert fs.row_for(sec) == expected_row


def test_korean_names_land_in_the_right_line():
    covered = Security(market="KR", ticker="441680",
                       display_name="TIGER 미국나스닥100커버드콜", currency="KRW")
    bond = Security(market="KR", ticker="385560",
                    display_name="KODEX 종합채권(AA-이상)액티브", currency="KRW")
    assert fs.row_for(covered) == "ST"
    assert fs.row_for(bond) == "DF"


# =====================================================================
# 자동 정리 -- 눌렀을 때만
# =====================================================================
def test_tidy_puts_each_kind_where_it_belongs():
    p = _p([("US", "JEPQ", "", 0.3), ("US", "SCHD", "", 0.3),
            ("US", "TLT", "", 0.2), ("US", "O", "", 0.2)])
    fs.tidy(p)
    assert _row(p, "JEPQ") == "ST"
    assert _row(p, "O") == "AM"
    assert _row(p, "SCHD") == "MC"
    assert _row(p, "TLT") == "DF"


def test_tidy_gives_the_biggest_holding_the_middle():
    """비중이 큰 종목이 가운데(C)로 갑니다."""
    p = _p([("US", "JEPQ", "", 0.1), ("US", "QYLD", "", 0.5)])
    fs.tidy(p)
    big = next(s for s in p.securities if s.ticker == "QYLD")
    assert pitch_grid.split(big.slot)[1] == "C"


def test_tidy_never_puts_two_in_one_slot():
    p = _p([("US", f"A{i:02d}", "", 0.02) for i in range(20)])
    fs.tidy(p)
    slots = [s.slot for s in p.securities]
    assert len(set(slots)) == len(slots)


def test_tidy_reports_how_many_it_moved():
    p = _p([("US", "TLT", "", 0.5)])
    moved_first = fs.tidy(p)
    assert moved_first >= 0
    assert fs.tidy(p) == 0, "이미 정리된 상태에서 또 옮기면 안 됩니다"


def test_tidy_is_not_called_on_its_own(market):
    """**이 파일에서 제일 중요한 테스트.** 화면을 그리기만 해도 배치가 바뀌면 안 됩니다."""
    market.set_fx(rate=1_000.0)
    market.set_us({"TLT": {"currency": "USD", "latest": 100.0},
                   "JEPQ": {"currency": "USD", "latest": 100.0}})
    p = _p([("US", "TLT", "", 0.5), ("US", "JEPQ", "", 0.5)])
    # 일부러 "틀린" 자리에 둡니다 -- 채권을 공격에, 커버드콜을 수비에.
    next(s for s in p.securities if s.ticker == "TLT").place_in_slot("ST-C")
    next(s for s in p.securities if s.ticker == "JEPQ").place_in_slot("DF-C")

    at = AppTest.from_file(APP_PATH, default_timeout=90)
    at.session_state["portfolio"] = p
    at.run()
    assert not at.exception

    after = at.session_state["portfolio"]
    assert _row(after, "TLT") == "ST", "앱이 멋대로 옮겼습니다"
    assert _row(after, "JEPQ") == "DF", "앱이 멋대로 옮겼습니다"


def test_the_button_actually_tidies(market):
    market.set_fx(rate=1_000.0)
    market.set_us({"TLT": {"currency": "USD", "latest": 100.0},
                   "JEPQ": {"currency": "USD", "latest": 100.0}})
    p = _p([("US", "TLT", "", 0.5), ("US", "JEPQ", "", 0.5)])
    next(s for s in p.securities if s.ticker == "TLT").place_in_slot("ST-C")
    next(s for s in p.securities if s.ticker == "JEPQ").place_in_slot("DF-C")

    at = AppTest.from_file(APP_PATH, default_timeout=90)
    at.session_state["portfolio"] = p
    at.run()
    [b for b in at.button if b.key == "tidy_btn"][0].click().run()
    assert not at.exception

    after = at.session_state["portfolio"]
    assert _row(after, "JEPQ") == "ST"
    assert _row(after, "TLT") == "DF"


# =====================================================================
# 포메이션 표기
# =====================================================================
def test_formation_counts_where_things_actually_are():
    p = _p([("US", "JEPQ", "", 0.3), ("US", "SCHD", "", 0.3), ("US", "TLT", "", 0.4)])
    fs.tidy(p)
    assert fs.formation(p) == "1-1-1"


def test_formation_does_not_hide_zeros():
    """"0-0-5" 는 전부 공격에 있다는 뜻이고, 그게 이 표기의 쓸모입니다."""
    p = _p([("US", f"JEP{i}", "", 0.2) for i in range(5)])
    for sec in p.securities:      # 전부 커버드콜 취급이 아니므로 직접 공격에 둡니다
        pass
    for sec, slot in zip(p.securities, ["ST-C", "ST-CL", "ST-CR", "ST-L", "ST-R"]):
        sec.place_in_slot(slot)
    assert fs.formation(p) == "0-0-5"


def test_no_holdings_no_formation():
    assert fs.formation(Portfolio(name="t")) == ""


def test_goalkeeper_counts_as_defense():
    p = _p([("US", "SGOV", "", 1.0)])
    p.securities[0].place_in_slot("GK-C")
    assert fs.formation(p) == "1-0-0"


# =====================================================================
# 주장 완장
# =====================================================================
def test_the_captain_is_the_biggest_holding():
    p = _p([("US", "SCHD", "", 0.2), ("US", "JEPQ", "", 0.5), ("US", "TLT", "", 0.3)])
    captain = next(s for s in p.securities if s.id == fs.captain_id(p))
    assert captain.ticker == "JEPQ"


def test_no_captain_when_nothing_is_held():
    assert fs.captain_id(Portfolio(name="t")) is None


def test_no_captain_when_every_weight_is_zero():
    """0% 만 담은 상태에서 아무에게나 완장을 채우면 뜻이 없습니다."""
    p = _p([("US", "SCHD", "", 0.0), ("US", "JEPQ", "", 0.0)])
    assert fs.captain_id(p) is None


def test_the_pitch_gets_told_who_the_captain_is():
    html = (pathlib.Path(__file__).resolve().parent.parent
            / "components" / "football_pitch" / "frontend" / "index.html"
            ).read_text(encoding="utf-8")
    assert "p.captain" in html                      # 화면
    assert "captain: !!p.captain" in html           # 값 받기
    assert html.count("#E8C34A") >= 1               # 캡처 이미지에도 같은 색


# =====================================================================
# 이름 추천
# =====================================================================
def _trailing_monthly(months: int = 12):
    """오늘부터 거꾸로 months 개월치 월배당 이력.

    ⚠ 연도를 고정해서 "2026-01..2026-12" 처럼 찍으면 미래 지급일이 섞여서 TTM
      구간(최근 365일) 밖으로 나갑니다. 그러면 12회를 넣었는데 9회만 세어져
      월배당이 분기배당으로 분류됩니다. 실제로 이 테스트가 그렇게 틀렸습니다.
    """
    import config
    today = config.today_local()
    pairs = []
    y, m = today.year, today.month
    for _ in range(months):
        m -= 1
        if m == 0:
            m, y = 12, y - 1
        pairs.append((f"{y}-{m:02d}-15", 1.0))
    return series(sorted(pairs))


def _comp_for(market, specs, n_payments=12):
    market.set_fx(rate=1_000.0)
    pays = _trailing_monthly(n_payments)
    market.set_us({t: {"currency": "USD", "latest": 100.0, "distributions": pays}
                   for mk, t, _n, _w in specs if mk == "US"})
    market.set_kr({t: {"currency": "KRW", "latest": 10_000.0, "distributions": pays}
                   for mk, t, _n, _w in specs if mk == "KR"})
    p = _p(specs)
    fs.tidy(p)
    return p, portfolio_service.compute(p)


def test_name_has_seed_schedule_and_shape(market):
    p, comp = _comp_for(market, [("US", "JEPQ", "", 0.5), ("US", "TLT", "", 0.5)])
    name = fs.suggest_name(p, comp)
    assert "1억" in name
    assert cs.SCHEDULE_MONTHLY in name
    assert fs.formation(p) in name


def test_name_works_without_a_computation():
    p = _p([("US", "JEPQ", "", 1.0)])
    fs.tidy(p)
    name = fs.suggest_name(p)
    assert "1억" in name and "0-0-1" in name


def test_name_of_an_empty_portfolio_is_just_the_seed():
    assert fs.suggest_name(Portfolio(name="t", initial_capital_krw=50_000_000)) == "5,000만"


def test_the_screen_offers_the_suggested_name(market):
    specs = [("US", "JEPQ", "", 0.5), ("US", "TLT", "", 0.5)]
    p, _ = _comp_for(market, specs)
    at = AppTest.from_file(APP_PATH, default_timeout=90)
    at.session_state["portfolio"] = p
    at.run()
    btn = [b for b in at.button if b.key == "name_suggest"]
    assert btn, "이름 추천 버튼이 없습니다"

    btn[0].click().run()
    assert not at.exception
    assert at.session_state["portfolio"].name != "t"
    assert "1억" in at.session_state["portfolio"].name
