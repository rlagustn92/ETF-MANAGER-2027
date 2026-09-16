"""공유 링크 (?p=...) 테스트.

이 기능의 입력은 **완전한 외부 입력**입니다. 누구든 주소를 손으로 고쳐서 보낼 수
있고, 받는 사람은 그걸 그냥 누릅니다. 그래서 여기서 지키는 것은 두 가지입니다.

1. **주소 하나로 남의 화면을 죽일 수 없다.** decode 는 무엇이 와도 예외를 안 냅니다.
2. **링크를 눌렀다고 남의 작업이 날아가지 않는다.** 배너만 뜨고, 눌러야 가져옵니다.
"""

from __future__ import annotations

import pathlib

import pytest
from streamlit.testing.v1 import AppTest

import config
from models.portfolio import Portfolio
from models.security import Security
from services import share_service, slot_service

APP_PATH = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")


def _portfolio(pairs) -> Portfolio:
    p = Portfolio(name="t", initial_capital_krw=10_000_000)
    for market, ticker, pct in pairs:
        p.add(Security(market=market, ticker=ticker,
                       currency="USD" if market == "US" else "KRW",
                       target_weight=pct / 100.0))
    return p


# =====================================================================
# 만들기
# =====================================================================
def test_encode_keeps_order_market_ticker_and_weight():
    p = _portfolio([("US", "SCHD", 30), ("KR", "458730", 20), ("US", "O", 15)])
    assert share_service.encode(p) == "US.SCHD:30,KR.458730:20,US.O:15"


def test_encode_drops_pointless_zeros_but_keeps_real_decimals():
    p = _portfolio([("US", "SCHD", 30), ("US", "JEPQ", 12.5), ("US", "O", 7.25)])
    assert share_service.encode(p) == "US.SCHD:30,US.JEPQ:12.5,US.O:7.25"


def test_encode_of_an_empty_portfolio_is_empty():
    assert share_service.encode(Portfolio(name="t")) == ""


def test_share_url_of_an_empty_portfolio_is_just_the_app():
    assert share_service.share_url(Portfolio(name="t")) == config.APP_PUBLIC_URL


def test_url_stays_short_enough_for_a_comment():
    """주소가 길면 댓글이 지저분해지고 잘리기도 합니다."""
    p = _portfolio([("US", f"AA{i:02d}", 4) for i in range(10)])
    assert len(share_service.share_url(p)) < 200


# =====================================================================
# 읽기 -- 무엇이 와도 안 죽는다
# =====================================================================
def test_decode_round_trips_what_encode_made():
    p = _portfolio([("US", "SCHD", 30), ("KR", "458730", 20.5)])
    got = share_service.decode(share_service.encode(p))
    assert [(i.market, i.ticker, i.weight_pct) for i in got] == [
        ("US", "SCHD", 30.0), ("KR", "458730", 20.5)]


def test_decode_handles_a_ticker_with_a_dot_in_it():
    """BRK.B 처럼 종목코드 안에도 점이 있습니다. 첫 점에서만 잘라야 합니다."""
    got = share_service.decode("US.BRK.B:25")
    assert [(i.market, i.ticker, i.weight_pct) for i in got] == [("US", "BRK.B", 25.0)]


@pytest.mark.parametrize("junk", [
    None, "", "   ", ",", ":", "...", "&&&",
    "hello world", "<script>alert(1)</script>",
    "US.SCHD", "SCHD:30", "US:30", ".SCHD:30", "US.:30",
    "XX.SCHD:30",                       # 모르는 시장
    "US.SCHD:많이", "US.SCHD:NaN", "US.SCHD:inf", "US.SCHD:-5",
    "US.SCHD:1e400",
    "US.'; DROP TABLE x; --:30",
    "US.SCHD" + "A" * 500 + ":30",      # 말도 안 되게 긴 종목코드
    "x" * 5000,                          # 길이 제한 초과
    123, [], {},                          # 애초에 문자열이 아님
])
def test_decode_never_raises_and_drops_junk(junk):
    assert share_service.decode(junk) == []


def test_decode_keeps_the_good_parts_and_drops_the_bad():
    got = share_service.decode("US.SCHD:30,쓰레기,XX.NOPE:10,KR.458730:20,US.O:않되")
    assert [(i.market, i.ticker) for i in got] == [("US", "SCHD"), ("KR", "458730")]


def test_decode_drops_duplicates_keeping_the_first():
    got = share_service.decode("US.SCHD:30,US.SCHD:99")
    assert len(got) == 1 and got[0].weight_pct == 30.0


def test_decode_caps_how_many_can_come_in():
    """전술판 슬롯보다 많이 받아봐야 자리가 없습니다."""
    text = ",".join(f"US.A{i:03d}:1" for i in range(200))
    assert len(share_service.decode(text)) == share_service.MAX_ITEMS


def test_decode_caps_a_single_weight_at_100():
    got = share_service.decode("US.SCHD:99999")
    assert got[0].weight_pct == 100.0


def test_decode_is_case_insensitive():
    got = share_service.decode("us.schd:30")
    assert [(i.market, i.ticker) for i in got] == [("US", "SCHD")]


# =====================================================================
# 전술로 만들기
# =====================================================================
def test_to_portfolio_uses_the_receivers_seed_not_the_senders():
    """남의 시드로 열어주면 받는 사람이 곧바로 지워야 합니다."""
    items = share_service.decode("US.SCHD:30,KR.458730:20")
    p = share_service.to_portfolio(items, name="받은 전술", initial_capital_krw=55_000_000)
    assert p.initial_capital_krw == 55_000_000
    assert p.name == "받은 전술"
    assert [s.ticker for s in p.securities] == ["SCHD", "458730"]
    assert [round(s.target_weight, 4) for s in p.securities] == [0.3, 0.2]


def test_to_portfolio_still_works_when_names_cannot_be_looked_up(monkeypatch):
    """검색 목록을 못 가져와도 종목코드로라도 열려야 합니다."""
    import data.providers.search_provider as sp

    def boom(*a, **k):
        raise RuntimeError("네트워크 없음")

    monkeypatch.setattr(sp, "resolve_us_ticker", boom)
    monkeypatch.setattr(sp, "search", boom)
    p = share_service.to_portfolio(share_service.decode("US.SCHD:30"),
                                   name="받은 전술", initial_capital_krw=1_000_000)
    assert [s.ticker for s in p.securities] == ["SCHD"]
    assert p.securities[0].display_name == "SCHD"


@pytest.fixture
def offline_names(monkeypatch):
    """이름 조회를 끕니다. 가짜 티커로 테스트할 때 yfinance 를 부르지 않도록."""
    monkeypatch.setattr(share_service, "_resolve_name",
                        lambda item: (item.ticker, item.ticker,
                                      "KRW" if item.market == "KR" else "USD"))


def test_to_portfolio_gives_everyone_a_pitch_slot(offline_names):
    items = share_service.decode(",".join(f"US.A{i:02d}:3" for i in range(12)))
    p = share_service.to_portfolio(items, name="t", initial_capital_krw=1_000_000)
    slots = [s.slot for s in p.securities]
    assert len(slots) == 12
    assert len(set(slots)) == 12, "두 종목이 같은 자리에 겹쳤습니다"


def test_a_big_shared_portfolio_does_not_lose_securities(offline_names):
    """보낸 사람은 '종목 더 담기' 로 26개까지 담을 수 있습니다.

    기본 한도(11명)를 안 올리면 12번째부터 조용히 사라지고, 받은 사람은 **뭘 못
    받았는지조차 모릅니다.** 실제로 테스트가 잡아낸 버그입니다.
    """
    items = share_service.decode(",".join(f"US.A{i:02d}:1" for i in range(20)))
    p = share_service.to_portfolio(items, name="t", initial_capital_krw=1_000_000)
    assert len(p.securities) == 20


def test_a_full_squad_shared_portfolio_arrives_whole(offline_names):
    items = share_service.decode(
        ",".join(f"US.A{i:02d}:1" for i in range(share_service.MAX_ITEMS)))
    p = share_service.to_portfolio(items, name="t", initial_capital_krw=1_000_000)
    assert len(p.securities) == share_service.MAX_ITEMS


def test_summary_says_what_you_are_about_to_get():
    items = share_service.decode("US.SCHD:30,KR.458730:20")
    assert share_service.summary(items) == "2종목 · 합계 50%"


# =====================================================================
# 화면 -- 링크로 들어온 사람
# =====================================================================
def _market(market):
    market.set_fx(rate=1_400.0)
    market.set_us({t: {"currency": "USD", "latest": 100.0}
                   for t in ("SCHD", "JEPQ", "O", "TLT", "VOO")})
    market.set_kr({"458730": {"currency": "KRW", "latest": 10_000.0}})


def _banner_texts(at):
    return " ".join(m.value for m in at.markdown)


def test_a_shared_link_only_offers_it_does_not_apply_it(market):
    """링크 하나로 남의 작업이 날아가면 안 됩니다. 배너만 뜨고 그대로 둡니다."""
    _market(market)
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.query_params["p"] = "US.SCHD:30,KR.458730:20"
    at.session_state["portfolio"] = _portfolio([("US", "TLT", 50)])
    at.run()

    assert not at.exception
    assert "누군가 공유한 전술입니다" in _banner_texts(at)
    # 원래 담겨 있던 것은 그대로
    assert [s.ticker for s in at.session_state["portfolio"].securities] == ["TLT"]


def test_adopting_a_shared_link_puts_it_in_a_new_slot(market):
    _market(market)
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.query_params["p"] = "US.SCHD:30,KR.458730:20"
    at.session_state["portfolio"] = _portfolio([("US", "TLT", 50)])
    at.run()

    [b for b in at.button if b.key == "share_adopt"][0].click().run()
    assert not at.exception
    assert len(at.session_state["slots"]) == 2
    assert [s.ticker for s in at.session_state["portfolio"].securities] == ["SCHD", "458730"]
    # 원래 칸은 살아 있어야 합니다
    assert at.session_state["slots"][0].security_count == 1


def test_adopting_into_an_empty_screen_uses_the_current_slot(market):
    """빈 화면으로 들어온 사람에게 칸을 새로 만들어줄 이유가 없습니다."""
    _market(market)
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.query_params["p"] = "US.SCHD:30"
    at.run()

    [b for b in at.button if b.key == "share_adopt"][0].click().run()
    assert not at.exception
    assert len(at.session_state["slots"]) == 1
    assert [s.ticker for s in at.session_state["portfolio"].securities] == ["SCHD"]


def test_the_banner_goes_away_after_adopting(market):
    """가져온 뒤에도 배너가 남아 있으면 새로고침할 때마다 잔소리가 됩니다."""
    _market(market)
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.query_params["p"] = "US.SCHD:30"
    at.run()
    [b for b in at.button if b.key == "share_adopt"][0].click().run()
    assert "누군가 공유한 전술입니다" not in _banner_texts(at)


def test_the_banner_can_be_dismissed_without_taking_anything(market):
    _market(market)
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.query_params["p"] = "US.SCHD:30"
    at.session_state["portfolio"] = _portfolio([("US", "TLT", 50)])
    at.run()

    [b for b in at.button if b.key == "share_dismiss"][0].click().run()
    assert not at.exception
    assert "누군가 공유한 전술입니다" not in _banner_texts(at)
    assert [s.ticker for s in at.session_state["portfolio"].securities] == ["TLT"]


@pytest.mark.parametrize("junk", ["", "쓰레기", "XX.NOPE:9", "<script>x</script>",
                                  "US.SCHD", "x" * 3000])
def test_a_broken_link_shows_no_banner_and_does_not_crash(market, junk):
    _market(market)
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.query_params["p"] = junk
    at.run()
    assert not at.exception
    assert "누군가 공유한 전술입니다" not in _banner_texts(at)


def test_a_shared_link_survives_a_full_round_trip(market):
    """내가 만든 링크를 남이 열면 내가 담은 그대로 나와야 합니다."""
    _market(market)
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["portfolio"] = _portfolio([("US", "SCHD", 30), ("KR", "458730", 20)])
    at.run()
    link = [c.value for c in at.code][0].rstrip().splitlines()[-1]

    at2 = AppTest.from_file(APP_PATH, default_timeout=60)
    at2.query_params["p"] = link.split("?p=", 1)[1]
    at2.run()
    [b for b in at2.button if b.key == "share_adopt"][0].click().run()

    assert not at2.exception
    got = at2.session_state["portfolio"].securities
    assert [(s.market, s.ticker, round(s.target_weight, 4)) for s in got] == [
        ("US", "SCHD", 0.3), ("KR", "458730", 0.2)]
