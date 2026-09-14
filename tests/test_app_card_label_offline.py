"""전술판 이름표 직접 수정 (네트워크 없이).

여기서 지키려는 것:
- 이름표 칸에 글자를 넣으면 **그 값이 실제로 전술판 카드에 반영**된다
- 비우면 자동 축약으로 되돌아간다
- 종목을 바꿔 선택해도 앞 종목의 이름표가 남지 않는다
"""

from __future__ import annotations

import pathlib

import pytest
from streamlit.testing.v1 import AppTest

import pitch_kit
from models.portfolio import Portfolio
from models.security import Security

APP_PATH = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")


def _portfolio() -> Portfolio:
    p = Portfolio(name="이름표", initial_capital_krw=10_000_000)
    p.add(Security(market="KR", ticker="458730", name="TIGER 미국배당다우존스",
                   display_name="TIGER 미국배당다우존스", currency="KRW", target_weight=0.5))
    p.add(Security(market="US", ticker="SCHD", currency="USD", target_weight=0.5))
    return p


def _run(market):
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    p = _portfolio()
    at.session_state["portfolio"] = p
    at.session_state["selected_id"] = p.securities[0].id
    at.run()
    return at, p


def _label_input(at):
    return next(t for t in at.text_input if t.label == "전술판 이름표")


def test_auto_label_is_shown_as_placeholder(market):
    at, p = _run(market)
    assert not at.exception
    # 기본값은 비어 있고, 자동으로 줄인 이름이 안내 문구로 보인다
    assert _label_input(at).value == ""
    assert p.securities[0].card_label == ""
    assert pitch_kit.card_label("KR", "458730", "TIGER 미국배당다우존스") == "미배당다우"


def test_typing_a_label_changes_the_card(market):
    at, p = _run(market)
    _label_input(at).set_value("내 주력").run()
    assert not at.exception
    sec = at.session_state["portfolio"].securities[0]
    assert sec.card_label == "내 주력"
    # 전술판에 실제로 내려가는 값
    assert pitch_kit.card_label(sec.market, sec.ticker, sec.display_name,
                                sec.card_label) == "내 주력"


def test_clearing_the_label_returns_to_auto(market):
    at, p = _run(market)
    _label_input(at).set_value("내 주력").run()
    _label_input(at).set_value("").run()
    assert not at.exception
    sec = at.session_state["portfolio"].securities[0]
    assert sec.card_label == ""
    assert pitch_kit.card_label(sec.market, sec.ticker, sec.display_name,
                                sec.card_label) == "미배당다우"


def test_label_belongs_to_its_own_security(market):
    """한 종목 이름표를 고친 뒤 다른 종목을 열었을 때 그 값이 따라오면 안 된다."""
    at, p = _run(market)
    _label_input(at).set_value("내 주력").run()

    at.session_state["selected_id"] = p.securities[1].id
    at.run()
    assert not at.exception
    assert _label_input(at).value == ""                        # 미국 종목은 비어 있어야
    assert at.session_state["portfolio"].securities[1].card_label == ""
    assert at.session_state["portfolio"].securities[0].card_label == "내 주력"
