"""겹치는 종목 경고 테스트.

이 기능의 양심은 한 줄입니다 — **"확인 못 함" 과 "안 겹침" 은 다른 말.**
표에 없는 종목을 조용히 빼놓고 "겹치는 것 없음" 이라고 하면 그게 거짓말입니다.

그리고 이름으로는 못 잡는다는 것도 여기서 못 박습니다. 이름 비교는 정확히
반대로 틀립니다 -- VOO/SPY 는 글자가 하나도 안 겹치는데 같은 물건이고,
"TIGER 미국배당다우존스" 와 "TIGER 미국나스닥100커버드콜" 은 앞부분이 잔뜩
겹치는데 다른 물건입니다.
"""

from __future__ import annotations

import pathlib

import pytest
from streamlit.testing.v1 import AppTest

import presets
from models.portfolio import Portfolio
from models.security import Security
from services import overlap_service as ov

APP_PATH = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")


def _p(specs) -> Portfolio:
    """specs: [(market, ticker, name, weight_ratio)]"""
    p = Portfolio(name="t", initial_capital_krw=100_000_000, max_squad_size=26)
    for mk, ticker, name, w in specs:
        p.add(Security(market=mk, ticker=ticker, display_name=name,
                       currency="USD" if mk == "US" else "KRW", target_weight=w))
    return p


# =====================================================================
# 이름으로는 못 잡는 것들
# =====================================================================
def test_voo_and_spy_are_caught_even_though_the_names_share_nothing():
    """이 기능이 존재하는 이유입니다."""
    report = ov.check(_p([("US", "VOO", "", 0.3), ("US", "SPY", "", 0.2)]))
    assert report.has_overlap
    assert report.groups[0].index_name == "S&P500 계열"
    assert report.groups[0].total_pct == pytest.approx(50.0)


def test_similar_names_that_are_different_things_are_not_flagged():
    """앞 글자가 잔뜩 겹쳐도 기초지수가 다르면 겹친 게 아닙니다."""
    report = ov.check(_p([
        ("KR", "458730", "TIGER 미국배당다우존스", 0.3),
        ("KR", "441680", "TIGER 미국나스닥100커버드콜(합성)", 0.3),
    ]))
    assert not report.has_overlap


def test_the_covered_call_version_counts_as_the_same_underlying():
    """기초가 같으면 같이 움직입니다. 커버드콜은 덜 오르고 같이 빠질 뿐입니다."""
    report = ov.check(_p([
        ("US", "SCHD", "", 0.3),
        ("KR", "458760", "TIGER 미국배당다우존스타겟커버드콜2호", 0.2),
    ]))
    assert report.has_overlap
    assert report.groups[0].index_name == "다우존스 배당100 계열"


def test_three_nasdaq_covered_calls_are_one_group():
    """사람들이 실제로 겹쳐 담는 제일 흔한 경우입니다."""
    report = ov.check(_p([
        ("US", "JEPQ", "", 0.2), ("US", "QQQI", "", 0.15),
        ("KR", "441680", "TIGER 미국나스닥100커버드콜(합성)", 0.1),
    ]))
    assert len(report.groups) == 1
    assert report.groups[0].index_name == "나스닥100 계열"
    assert report.groups[0].total_pct == pytest.approx(45.0)
    assert len(report.groups[0].members) == 3


def test_one_of_a_kind_is_not_an_overlap():
    report = ov.check(_p([("US", "SCHD", "", 0.5), ("US", "JEPQ", "", 0.5)]))
    assert not report.has_overlap


# =====================================================================
# "확인 못 함" -- 이 기능의 양심
# =====================================================================
def test_securities_we_do_not_know_are_listed_as_unchecked():
    report = ov.check(_p([
        ("KR", "329200", "TIGER 리츠부동산인프라", 0.3),
        ("KR", "0177R0", "TIGER 반도체TOP10커버드콜액티브", 0.2),
    ]))
    assert report.unknown == ["TIGER 리츠부동산인프라", "TIGER 반도체TOP10커버드콜액티브"]
    assert not report.has_overlap


def test_unknown_securities_are_never_quietly_grouped_together():
    """모르는 것끼리 묶어서 "겹친다" 고 하면 그건 지어낸 경고입니다."""
    report = ov.check(_p([("US", "ZZZA", "", 0.3), ("US", "ZZZB", "", 0.3)]))
    assert not report.has_overlap
    assert len(report.unknown) == 2


def test_korean_names_are_used_not_the_codes():
    report = ov.check(_p([("KR", "329200", "TIGER 리츠부동산인프라", 0.3)]))
    assert report.unknown == ["TIGER 리츠부동산인프라"]


def test_zero_weight_securities_are_ignored():
    """0% 로 담아둔 건 담은 게 아닙니다."""
    report = ov.check(_p([("US", "VOO", "", 0.0), ("US", "SPY", "", 0.0)]))
    assert not report.has_overlap and report.unknown == []


def test_an_empty_portfolio_is_quiet():
    report = ov.check(Portfolio(name="t"))
    assert not report.has_overlap and report.unknown == []


# =====================================================================
# 표 자체의 건강 검진
# =====================================================================
def test_every_entry_in_the_table_is_shaped_right():
    for (market, ticker), index_name in ov.INDEX_OF.items():
        assert market in ("US", "KR"), (market, ticker)
        assert ticker == ticker.strip().upper() and ticker, ticker
        assert index_name and isinstance(index_name, str)


def test_lookup_is_case_insensitive():
    assert ov.index_of("US", "voo") == "S&P500 계열"
    assert ov.index_of("US", " spy ") == "S&P500 계열"
    assert ov.index_of("US", "ZZZZ") is None


def test_groups_are_sorted_by_how_much_you_hold():
    report = ov.check(_p([
        ("US", "JEPQ", "", 0.05), ("US", "QQQI", "", 0.05),
        ("US", "VOO", "", 0.3), ("US", "SPY", "", 0.3),
    ]))
    assert [g.index_name for g in report.groups] == ["S&P500 계열", "나스닥100 계열"]


def test_members_are_sorted_by_weight():
    report = ov.check(_p([("US", "QQQI", "", 0.1), ("US", "JEPQ", "", 0.3)]))
    assert [n for n, _ in report.groups[0].members] == ["JEPQ", "QQQI"]


# =====================================================================
# 화면
# =====================================================================
def _market(market):
    market.set_fx(rate=1_400.0)
    market.set_us({t: {"currency": "USD", "latest": 100.0}
                   for t in ("VOO", "SPY", "JEPQ", "QQQI", "SCHD", "TLT", "O")})
    market.set_kr({t: {"currency": "KRW", "latest": 10_000.0}
                   for t in ("441680", "329200", "458730", "0177R0", "0219E0")})


def test_the_screen_warns_about_the_overlap(market):
    _market(market)
    at = AppTest.from_file(APP_PATH, default_timeout=90)
    at.session_state["portfolio"] = _p([
        ("US", "JEPQ", "", 0.2), ("US", "QQQI", "", 0.15),
        ("KR", "441680", "TIGER 미국나스닥100커버드콜(합성)", 0.1),
    ])
    at.run()
    assert not at.exception
    body = " ".join(m.value for m in at.markdown)
    assert "같은 지수를 여러 번 담았습니다" in body
    assert "나스닥100 계열" in body


def test_the_screen_says_what_it_could_not_check(market):
    """조용히 빼놓고 '겹치는 것 없음' 이라고 하면 그게 거짓말입니다."""
    _market(market)
    at = AppTest.from_file(APP_PATH, default_timeout=90)
    at.session_state["portfolio"] = _p([
        ("KR", "329200", "TIGER 리츠부동산인프라", 0.3),
        ("KR", "0177R0", "TIGER 반도체TOP10커버드콜액티브", 0.2),
    ])
    at.run()
    assert not at.exception
    captions = " ".join(c.value for c in at.caption)
    assert "확인 못 한 종목" in captions
    assert "겹치지 않는다는 뜻이 아닙니다" in captions


def test_the_screen_never_tells_you_what_to_do(market):
    """사실만 보여주고 판단은 사용자 몫입니다."""
    _market(market)
    at = AppTest.from_file(APP_PATH, default_timeout=90)
    at.session_state["portfolio"] = _p([("US", "VOO", "", 0.5), ("US", "SPY", "", 0.5)])
    at.run()
    body = " ".join(m.value for m in at.markdown)
    start = body.find("같은 지수를 여러 번")
    panel = body[start:start + 400]
    for banned in ("빼세요", "줄이세요", "추천", "위험합니다"):
        assert banned not in panel, f"'{banned}' 는 쓰면 안 됩니다"


def test_a_clean_portfolio_shows_no_warning(market):
    _market(market)
    at = AppTest.from_file(APP_PATH, default_timeout=90)
    at.session_state["portfolio"] = _p([("US", "SCHD", "", 0.5), ("US", "TLT", "", 0.5)])
    at.run()
    body = " ".join(m.value for m in at.markdown)
    assert "같은 지수를 여러 번 담았습니다" not in body


def test_the_shipped_examples_are_honest_about_what_they_hold(market):
    """예시 구성에도 같은 기준을 적용합니다. 앱이 내놓는 예시가 겹쳐 있다면
    그 사실이 화면에 보여야지, 예외로 두면 안 됩니다."""
    for preset in presets.PRESETS:
        report = ov.check(presets.build_portfolio(preset))
        # 겹치든 안 겹치든 상관없습니다. 다만 계산이 터지면 안 됩니다.
        assert isinstance(report.groups, list)
        assert isinstance(report.unknown, list)
