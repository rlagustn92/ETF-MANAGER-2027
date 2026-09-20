"""종목 상세 패널의 네이버 증권 바로가기 (네트워크 없음).

사용자 요청: 기존 토스·야후 옆에 네이버 증권을 하나 더 답니다.
여기서 지키려는 것:

- 한국·미국 모두 **진짜 주소**가 나간다 (문구만 있고 주소가 빠지면 아무 데도 안 갑니다)
- 주소를 확인하지 못하면 **링크를 아예 안 그린다** — 지어낸 주소로 빈 페이지에
  보내는 것보다 없는 편이 낫습니다 (프로젝트 절대 규칙)
- 기존 토스·야후는 그대로 남는다
- 새 창으로 열리고 rel=noopener 가 붙는다 (탭 가로채기 방지)
"""

from __future__ import annotations

import pathlib

from streamlit.testing.v1 import AppTest

from data.providers import cache
from models.portfolio import Portfolio
from models.security import Security
from services import naver_link_service as nls

APP_PATH = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")


def _run(market, *, which=0):
    cache.invalidate("naver:")
    p = Portfolio(name="바로가기", initial_capital_krw=10_000_000)
    p.add(Security(market="KR", ticker="458730", name="TIGER 미국배당다우존스",
                   display_name="TIGER 미국배당다우존스", currency="KRW", target_weight=0.5))
    p.add(Security(market="US", ticker="SCHD", currency="USD", target_weight=0.5))
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["portfolio"] = p
    at.session_state["selected_id"] = p.securities[which].id
    at.run()
    assert not at.exception
    return at


def _link_block(at) -> str:
    """종목 상세 패널 맨 위의 이름 + 바로가기 줄."""
    return next(m.value for m in at.markdown if "토스 ↗" in m.value)


def test_korean_security_gets_a_naver_link(market):
    block = _link_block(_run(market, which=0))
    assert "네이버 ↗" in block
    assert "href='https://m.stock.naver.com/domestic/stock/458730/total'" in block


def test_us_security_gets_a_naver_link(market):
    block = _link_block(_run(market, which=1))
    assert "네이버 ↗" in block
    assert "href='https://m.stock.naver.com/worldstock/etf/SCHD.K'" in block


def test_the_existing_links_are_still_there(market):
    block = _link_block(_run(market, which=1))
    assert "토스 ↗" in block and "야후 ↗" in block
    # 네이버가 맨 뒤에 붙습니다(기존 순서를 흔들지 않음)
    assert block.index("토스 ↗") < block.index("야후 ↗") < block.index("네이버 ↗")


def test_it_opens_in_a_new_tab_safely(market):
    block = _link_block(_run(market, which=0))
    naver_anchor = block[block.index("m.stock.naver.com") - 200:]
    assert "target='_blank'" in naver_anchor
    assert "rel='noopener noreferrer'" in naver_anchor


def test_no_link_is_drawn_when_the_address_cannot_be_confirmed(market, monkeypatch):
    """주소를 못 찾으면 네이버 칩만 사라지고, 나머지 화면은 멀쩡합니다."""
    monkeypatch.setattr(nls, "naver_url", lambda *a, **k: None)
    block = _link_block(_run(market, which=1))
    assert "네이버 ↗" not in block
    assert "토스 ↗" in block and "야후 ↗" in block


def test_the_panel_does_not_hit_the_network_for_seeded_tickers(market, monkeypatch):
    """화면을 그릴 때마다 남의 서버를 두드리면 안 됩니다.

    한국은 조립, 자주 쓰는 미국 종목은 미리 받아둔 표에서 나오므로 호출이 0번입니다.
    """
    # requests 모듈 자체를 막으면 방문자 카운터까지 걸리므로, 네이버 조회 경로만 막습니다.
    def _explode(*a, **k):
        raise AssertionError("상세 패널이 네이버를 호출했습니다.")
    monkeypatch.setattr(nls, "_lookup_us", _explode)
    for which in (0, 1):
        assert "네이버 ↗" in _link_block(_run(market, which=which))
