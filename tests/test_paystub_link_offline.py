"""자매 서비스(MY ETF 급여명세서) 바로가기 (네트워크 없음).

사용자 요청: "포트폴리오 다 짜고 관리할땐? MY ETF 급여명세서" 바로가기를 두 곳에.
  1) 화면 맨 위 제목 옆, 기존 'ETF 뭐살까 고민될땐? ETF INSIDE' 링크 **오른쪽**
  2) 맨 아래 '포트폴리오 요약 (상세)' 제목 **바로 위** (제목만 한 크기, 초록 글씨)
여기서 지키려는 것:

- 진짜 링크가 나간다 (문구만 있고 주소가 빠지면 아무 데도 안 갑니다)
- 주소·문구는 config 한 곳에서만 온다 (한 줄 고치면 화면이 같이 바뀐다)
- 고르는 곳(INSIDE) 다음에 관리하는 곳(급여명세서) 순서로 놓인다
- 새 창으로 열리고 rel=noopener 가 붙는다 (탭 가로채기 방지)
"""

from __future__ import annotations

import inspect
import pathlib

from streamlit.testing.v1 import AppTest

import config
import ui_theme

APP_PATH = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")


def _run(market):
    market.set_fx(rate=1_300.0)
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.run()
    assert not at.exception
    return at


def _paystub_blocks(at) -> list[str]:
    return [m.value for m in at.markdown if config.PAYSTUB_URL in m.value]


def _title_block(at) -> str:
    blocks = [b for b in _paystub_blocks(at) if "ETF MANAGER" in b]
    assert len(blocks) == 1, f"제목 옆 한 곳이어야 합니다: {len(blocks)}"
    return blocks[0]


def _summary_cta_block(at) -> str:
    blocks = [b for b in _paystub_blocks(at) if "paystub-cta" in b]
    assert len(blocks) == 1, f"요약 위 한 곳이어야 합니다: {len(blocks)}"
    return blocks[0]


def test_link_sits_right_of_the_inside_link(market):
    block = _title_block(_run(market))
    assert "ETF MANAGER" in block, block
    # 고르는 곳 -> 관리하는 곳 순서
    assert block.index(config.INSIDE_URL) < block.index(config.PAYSTUB_URL), block


def test_label_and_url_come_from_config(market):
    blocks = _paystub_blocks(_run(market))
    assert len(blocks) == 2, f"제목 옆/요약 위 두 곳이어야 합니다: {len(blocks)}"
    for block in blocks:
        assert f"href='{config.PAYSTUB_URL}'" in block, block
        assert f"{config.PAYSTUB_LABEL} ↗" in block, block
    assert config.PAYSTUB_URL.startswith("https://")
    assert "급여명세서" in config.PAYSTUB_LABEL


def test_cta_sits_right_above_the_summary_heading(market):
    """'포트폴리오 요약 (상세)' 제목 **바로 위**여야 합니다. 순서가 밀리면
    다 짠 뒤에 눌러야 할 버튼이 엉뚱한 곳에 있게 됩니다."""
    at = _run(market)
    values = [m.value for m in at.markdown]
    cta = values.index(_summary_cta_block(at))
    heading = next(i for i, v in enumerate(values) if v.strip() == "### 포트폴리오 요약 (상세)")
    assert heading == cta + 1, f"바로 위가 아닙니다: cta={cta}, heading={heading}"


def test_cta_looks_like_a_button_not_bare_text(market):
    """사용자 요청: 제목만 한 크기에 초록 글씨로, 다만 맨 글자 링크가 아니라
    테두리로 감싸고 은은한 초록 바탕을 깔아 '눌러도 되는 것'처럼 보이게.
    클래스만 붙이고 CSS 를 빠뜨리면 그냥 파란 기본 링크로 나옵니다."""
    assert "paystub-cta" in _summary_cta_block(_run(market))
    css = inspect.getsource(ui_theme.inject)
    assert ".paystub-cta {" in css
    # 옆 제목(h3=18px)과 비슷한 크기
    assert "h3, h4 {{ font-size: 18px !important; }}" in css
    assert "font-size: 16.5px; font-weight: 700" in css
    # 초록 글씨 + 테두리 + 은은한 초록 바탕 + 누를 수 있어 보이는 hover
    assert "color: #146b43 !important" in css
    assert "border-radius: 12px" in css
    assert "linear-gradient(180deg, rgba(28, 122, 75," in css
    assert ".paystub-cta:hover {" in css


def test_opens_in_a_new_tab_safely(market):
    for block in _paystub_blocks(_run(market)):
        assert "target='_blank'" in block, block
        assert "rel='noopener noreferrer'" in block, block


def test_chip_has_its_own_style(market):
    """옆의 ETF INSIDE 와 색이 달라야 서로 다른 곳이라는 게 보입니다.
    클래스만 붙이고 CSS 를 빠뜨리면 두 칩이 똑같이 보여 구분이 안 됩니다."""
    block = _title_block(_run(market))
    assert "ext-link paystub" in block, block
    assert ".ext-link.paystub" in inspect.getsource(ui_theme.inject)


def test_two_sister_chips_stay_together_but_unstack_on_phones(market):
    """두 칩은 한 덩어리(nowrap)로 묶여 나란히 붙어 있습니다. 다만 휴대폰 폭에서는
    묶인 채로 두면 오른쪽 칩이 화면 밖으로 잘려 눌러볼 수조차 없어서, 좁아지면
    묶음을 푸는 규칙이 있어야 합니다(실제 브라우저 375px 에서 확인한 문제)."""
    block = _title_block(_run(market))
    assert "sister-links" in block, block
    css = inspect.getsource(ui_theme.inject)
    assert ".sister-links {" in css
    assert "@media (max-width: 640px)" in css
    assert "white-space: normal" in css
