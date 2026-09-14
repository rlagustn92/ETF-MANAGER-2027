"""'어떻게 살까? (종목별 상세)' 표의 합계 줄과, 제목 옆 버전 표시 테스트 (네트워크 없음).

사용자 요청:
- 표 맨 아래에 돈 합계가 항상 집계되어야 한다.
- 화면 맨 위 제목 옆에 프로그램 버전(config.APP_VERSION)이 보여야 한다.
"""

from __future__ import annotations

import pathlib

from streamlit.testing.v1 import AppTest

import config
from models.portfolio import Portfolio
from models.security import Security

APP_PATH = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")

PRICE_A_KRW = 100_000.0      # 1주 100,000원 (KR 종목)
PRICE_B_USD = 100.0          # 1주 100 USD, 환율 1,000 -> 100,000원
FX = 1_000.0
CAPITAL = 10_000_000


def _run(market):
    market.set_fx(rate=FX)
    market.set_kr({"000001": {"currency": "KRW", "latest": PRICE_A_KRW}})
    market.set_us({"B": {"currency": "USD", "latest": PRICE_B_USD}})

    p = Portfolio(name="t", initial_capital_krw=CAPITAL)
    p.add(Security(market="KR", ticker="000001", name="가나다", display_name="가나다",
                   currency="KRW", target_weight=0.30))     # 300만 -> 30주
    p.add(Security(market="US", ticker="B", currency="USD", target_weight=0.20))  # 200만 -> 20주

    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["portfolio"] = p
    at.run()
    assert not at.exception
    return at


def test_table_has_total_row_summing_money_columns(market):
    at = _run(market)

    df = at.dataframe[0].value
    assert df["종목"].iloc[-1] == "합계"          # 항상 마지막 줄

    total = df.iloc[-1]
    # 30주 x 100,000 + 20주 x 100,000 = 5,000,000
    assert total["종목 원금(₩)"] == "5,000,000"
    assert total["살(BUY) 비율"] == "50.00%"
    assert total["실제로 들어간 비율"] == "50.00%"

    # 종목마다 통화/가격이 달라 더하면 틀리는 칸은 비워 둔다
    assert total["현재가"] == ""
    assert total["수량"] == ""
    assert total["통화"] == ""


def test_total_row_matches_portfolio_summary_metric(market):
    """표의 합계와 아래 '총 원금' 지표가 어긋나면 안 된다."""
    at = _run(market)

    total_in_table = at.dataframe[0].value["종목 원금(₩)"].iloc[-1]
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["총 원금"] == f"₩{total_in_table}"


def test_summary_strip_shows_all_six_numbers_in_one_box(market):
    """전술판 위 요약은 '·' 로 길게 이어 쓰지 않고 한 칸짜리 박스로 그립니다."""
    at = _run(market)

    strip = [m.value for m in at.markdown if m.value.startswith("<div class='stat-strip'>")]
    assert len(strip) == 1, "요약 박스는 화면에 하나만 있어야 합니다."
    # 마지막 칸은 '투자금 대비' (시드가 아니라 실제 투자금 기준 -- 라벨과 분모가 일치해야 함)
    for label in ("내 시드", "총 원금", "잔여현금", "월 분배금", "연 분배금",
                  "투자금 대비 분배율"):
        assert f"<div class='k'>{label}</div>" in strip[0], label

    # 값도 실제 계산 결과와 같아야 한다 (시드 1천만, 30주+20주 x 100,000 = 500만 투자)
    assert f"<div class='v'>₩{CAPITAL:,.0f}</div>" in strip[0]
    assert "<div class='v'>₩5,000,000</div>" in strip[0]


def test_negative_cash_is_marked_in_the_strip(market):
    """시드를 넘겨 담으면 잔여현금이 마이너스가 되고, 빨갛게 표시되어야 합니다."""
    market.set_fx(rate=FX)
    market.set_kr({"000001": {"currency": "KRW", "latest": PRICE_A_KRW}})
    market.set_us({"B": {"currency": "USD", "latest": PRICE_B_USD}})

    p = Portfolio(name="t", initial_capital_krw=CAPITAL, strict_capital_limit=False)
    p.add(Security(market="KR", ticker="000001", name="가나다", display_name="가나다",
                   currency="KRW", target_weight=0.80))
    p.add(Security(market="US", ticker="B", currency="USD", target_weight=0.80))

    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["portfolio"] = p
    at.run()
    assert not at.exception

    strip = [m.value for m in at.markdown if m.value.startswith("<div class='stat-strip'>")][0]
    assert "class='v neg'" in strip, strip


def test_version_is_shown_next_to_the_title(market):
    at = _run(market)

    titles = [m.value for m in at.markdown if "ETF MANAGER" in m.value]
    assert titles, "제목을 찾지 못했습니다."
    assert config.app_version_label() in titles[0], titles[0]
    assert config.app_version_label() == f"v{config.APP_VERSION}"
