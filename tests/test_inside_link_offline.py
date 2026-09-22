"""자매 서비스(ETF INSIDE) 바로가기 두 자리 (네트워크 없음).

사용자 요청: 새로 연 베타 서비스로 가는 버튼을
  1) 화면 맨 위 제목 옆 (개발자 피드백 링크 바로 오른쪽)
  2) 왼쪽 '종목 검색' 바로 아래
두 곳에 둡니다. 여기서 지키려는 것:

- 두 자리 모두에 **진짜 링크**가 나간다 (문구만 있고 주소가 빠지면 아무 데도 안 갑니다)
- 주소·문구는 config 한 곳에서만 온다 (한 줄 고치면 두 곳이 같이 바뀐다)
- 새 창으로 열리고 rel=noopener 가 붙는다 (탭 가로채기 방지)
"""

from __future__ import annotations

import pathlib

from streamlit.testing.v1 import AppTest

import config

APP_PATH = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")


def _run(market):
    market.set_fx(rate=1_300.0)
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.run()
    assert not at.exception
    return at


def _inside_blocks(at) -> list[str]:
    return [m.value for m in at.markdown if config.INSIDE_URL in m.value]


def test_link_appears_in_both_places(market):
    at = _run(market)
    blocks = _inside_blocks(at)
    assert len(blocks) == 2, f"제목 옆/종목 검색 아래 두 곳이어야 합니다: {len(blocks)}"

    title = next(b for b in blocks if "ETF MANAGER" in b)
    search = next(b for b in blocks if "ETF MANAGER" not in b)

    # 제목 옆: 기존 피드백 링크 '오른쪽'에 붙는다
    assert title.index(config.FEEDBACK_URL) < title.index(config.INSIDE_URL)
    # 종목 검색 쪽: 좁은 칸이라 한 줄짜리 버튼(block)으로 눕힌다
    assert "ext-link inside block" in search, search


def test_label_and_url_come_from_config(market):
    at = _run(market)
    for block in _inside_blocks(at):
        assert f"href='{config.INSIDE_URL}'" in block, block
        assert f"{config.INSIDE_LABEL} ↗" in block, block
    assert config.INSIDE_URL.startswith("https://")
    assert "BETA" in config.INSIDE_LABEL


def test_chips_have_no_leftover_underline(market):
    """칩은 테두리로 감싼 버튼 모양입니다. 밑줄이 남으면 옛날 링크처럼 보입니다.
    Streamlit 기본 스타일이 markdown 안의 <a> 에 더 강한 우선순위로 밑줄을 긋기
    때문에, none 만으로는 꺼지지 않고 !important 가 있어야 합니다(화면에서 확인)."""
    import inspect

    import ui_theme

    css = inspect.getsource(ui_theme.inject)
    assert "text-decoration: none !important;" in css


def test_opens_in_a_new_tab_safely(market):
    at = _run(market)
    for block in _inside_blocks(at):
        assert "target='_blank'" in block, block
        assert "rel='noopener noreferrer'" in block, block
