"""댓글용 텍스트 (네트워크 없이).

네이버 댓글처럼 이미지 첨부가 아예 안 되는 곳에서 쓰라고 만든 기능이라,
"글자만으로 포트폴리오가 전달되는가" 가 전부입니다.

특히 캡처 이미지와 **같은 숫자**여야 합니다. 같은 포트폴리오를 이미지로도 올리고
글로도 올렸는데 숫자가 다르면 신뢰를 잃습니다.
"""

from __future__ import annotations

import pathlib

import pytest
from streamlit.testing.v1 import AppTest

from formatting import pct, won_short
from models.portfolio import Portfolio
from models.security import Security
from services import portfolio_service

APP_PATH = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")


def _portfolio() -> Portfolio:
    p = Portfolio(name="월배당 공격형", initial_capital_krw=10_000_000)
    p.add(Security(market="US", ticker="SCHD", currency="USD", target_weight=0.6))
    p.add(Security(market="KR", ticker="458730", name="TIGER 미국배당다우존스",
                   display_name="TIGER 미국배당다우존스", currency="KRW", target_weight=0.4))
    return p


def _text(at) -> str:
    blocks = [c.value for c in at.code]
    assert blocks, "댓글용 텍스트 블록이 화면에 없습니다"
    return blocks[0]


def _run(market):
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["portfolio"] = _portfolio()
    at.run()
    assert not at.exception
    return at


def test_text_has_name_totals_and_every_holding(market):
    at = _run(market)
    txt = _text(at)

    assert "월배당 공격형" in txt
    assert "ETF MANAGER 2027" in txt
    # 담은 종목이 하나도 빠지면 안 됨
    assert "SCHD" in txt
    assert "TIGER 미국배당다우존스 (458730)" in txt


def test_numbers_match_the_computation(market):
    """캡처 이미지와 같은 값을 써야 합니다(둘 다 won_short / pct 를 씁니다)."""
    at = _run(market)
    txt = _text(at)
    comp = portfolio_service.compute(_portfolio())

    assert won_short(comp.total_actual_investment_krw) in txt
    assert won_short(comp.monthly_distribution_krw) in txt
    assert won_short(comp.annual_distribution_krw) in txt
    assert pct(comp.income_yield_on_invested_pct) in txt


def test_text_always_says_pre_tax_and_the_date(market):
    """이미지든 글이든 맥락 없이 퍼지므로, 세전이라는 점과 기준일이 꼭 붙어야 합니다.
    미국 15% 원천징수·국내 15.4% 배당소득세를 실수령으로 오해하면 손해입니다."""
    import config
    txt = _text(_run(market))
    assert "세전" in txt
    assert f"{config.today_local():%Y-%m-%d}" in txt


def test_text_ends_with_the_app_address(market):
    """댓글로 퍼질 때 어디서 만든 건지 따라올 수 있어야 합니다."""
    import config
    assert _text(_run(market)).rstrip().endswith(config.APP_PUBLIC_URL)


def test_holdings_are_ordered_by_weight(market):
    """비중 큰 종목이 위로. 캡처 이미지의 명단과 순서가 같아야 합니다."""
    txt = _text(_run(market))
    assert txt.index("SCHD") < txt.index("TIGER 미국배당다우존스")


def test_no_text_block_when_nothing_is_held(market):
    """빈 전술에서 '· 아무것도 없음' 만 든 텍스트를 내놓으면 민망합니다."""
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["portfolio"] = Portfolio(name="빈 전술", initial_capital_krw=10_000_000)
    at.run()
    assert not at.exception
    assert not [c for c in at.code], "종목이 없으면 댓글용 텍스트를 띄우지 않아야 합니다"
