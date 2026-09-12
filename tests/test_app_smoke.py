"""app.py 스모크 테스트 (Streamlit AppTest).

실제 위젯 상호작용을 시뮬레이션해서, 화면 요소들이 올바른 "실행 순서"로
배치되어 있는지 검증합니다. 특히:

- "선택 종목 상세" 패널의 목표비중 슬라이더(compute() 이전에 실행되어야 함)를
  바꿨을 때, 같은 렌더에서 위쪽 요약 바 / 지표 / 하단 표까지 전부 새 값으로
  갱신되는지 확인합니다. (브라우저에서는 커스텀 슬라이더의 드래그를 자동화로
  재현하기 까다로워, Streamlit 공식 테스트 API 로 직접 검증합니다.)

실제 yfinance 가격을 조회하므로 네트워크가 필요합니다 (pytest -m network).
"""

from __future__ import annotations

import pathlib

import pytest
from streamlit.testing.v1 import AppTest

pytestmark = pytest.mark.network

APP_PATH = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")


def _strip_cell(strip_html: str, label: str) -> str:
    """위쪽 요약 박스(.stat-strip)에서 라벨에 해당하는 값을 뽑아낸다."""
    import re
    m = re.search(rf"<div class='k'>{re.escape(label)}</div>"
                  rf"<div class='v[^']*'>([^<]*)</div>", strip_html)
    assert m, f"요약 박스에서 '{label}' 칸을 찾지 못했습니다: {strip_html[:300]}"
    return m.group(1)


def _add_qqq(at: AppTest) -> AppTest:
    search_box = [w for w in at.text_input if w.label == "검색어"][0]
    search_box.set_value("QQQ").run()
    search_btn = [b for b in at.button if b.label == "검색"][0]
    search_btn.click().run()
    add_btn = [b for b in at.button if b.label.startswith("＋ QQQ —")][0]
    add_btn.click().run()
    return at


def test_app_loads_without_exception():
    at = AppTest.from_file(APP_PATH, default_timeout=60).run()
    assert not at.exception


def test_initial_capital_shows_thousands_separators():
    at = AppTest.from_file(APP_PATH, default_timeout=60).run()
    cap_box = [w for w in at.text_input if w.label == "내 시드 (₩)"][0]
    assert cap_box.value == "100,000,000"


def test_weight_slider_edit_propagates_to_summary_and_metrics_same_run():
    """compute() 앞에서 실행되는 목표비중 슬라이더가, 같은 렌더에서
    위쪽 요약 바 / 지표 / 표에 즉시 반영되는지 확인 (사용자 피드백으로 도입된
    Phase A(편집)/Phase B(표시) 순서 분리가 실제로 동작하는지에 대한 회귀 테스트).
    """
    at = AppTest.from_file(APP_PATH, default_timeout=60).run()
    at = _add_qqq(at)
    assert not at.exception

    slider = [s for s in at.slider if s.label == "살(BUY) 비율 (%)"][0]
    assert slider.value == 0.0
    slider.set_value(20.0).run()
    assert not at.exception

    metrics = {m.label: m.value for m in at.metric}
    assert metrics["살(BUY) 비율"] == "20.00%"
    assert metrics["보유 주식 수"] != "0"          # 정수주 계산이 실제로 일어났어야 함
    assert metrics["이 종목에 들어간 돈"] != "₩0"

    # 위쪽 한 줄 요약 박스(.stat-strip)에도 같은 렌더에서 반영되어야 한다
    strip = [m.value for m in at.markdown if m.value.startswith("<div class='stat-strip'>")]
    assert strip, "위쪽 간략 요약 바를 찾지 못했습니다."
    assert _strip_cell(strip[0], "총 원금") != "₩0"


def test_distribution_yield_metric_shown_and_breakdown_expander_present():
    """QQQ 는 실제 분배 이력이 있으므로 '분배율 (TTM)' 지표가 '데이터 없음'이 아니어야 하고,
    산출 내역(지급일별 내역) expander 도 함께 떠야 한다."""
    at = AppTest.from_file(APP_PATH, default_timeout=60).run()
    at = _add_qqq(at)
    assert not at.exception

    metrics = {m.label: m.value for m in at.metric}
    assert "분배율 (TTM)" in metrics
    assert metrics["분배율 (TTM)"] != "데이터 없음"
    assert metrics["분배율 (TTM)"].endswith("%")

    expander_titles = [e.label for e in at.expander]
    assert any("분배율은 어떻게 계산됐나요" in t for t in expander_titles), expander_titles


def test_holdings_list_reflects_weight_after_next_rerun():
    """왼쪽 '보유 종목' 목록은 오른쪽 슬라이더보다 먼저 렌더링되므로 한 렌더 늦게
    반영된다 -- 슬라이더 조작 "다음" 렌더에서는 정확히 일치해야 한다."""
    at = AppTest.from_file(APP_PATH, default_timeout=60).run()
    at = _add_qqq(at)
    slider = [s for s in at.slider if s.label == "살(BUY) 비율 (%)"][0]
    slider.set_value(20.0).run()

    # 아무 위젯이나 한 번 더 건드려 다음 렌더를 유도 (분배금 포함 체크박스 토글 후 원복)
    cb = [c for c in at.checkbox if c.label == "분배금 계산에 넣기"][0]
    cb.set_value(cb.value).run()

    holdings_buttons = [b for b in at.button if "QQQ" in b.label and "%" in b.label]
    assert holdings_buttons, "보유 종목 목록에서 QQQ 버튼을 찾지 못했습니다."
    assert "20.00%" in holdings_buttons[0].label


def test_weight_slider_and_number_input_stay_in_sync():
    """목표비중 슬라이더 옆 '직접입력(%)' 숫자칸이 서로 값을 주고받는지 확인."""
    at = AppTest.from_file(APP_PATH, default_timeout=60).run()
    at = _add_qqq(at)

    slider = [s for s in at.slider if s.label == "살(BUY) 비율 (%)"][0]
    slider.set_value(35.0).run()
    num = [n for n in at.number_input if n.label == "직접입력(%)"][0]
    assert num.value == 35.0

    num = [n for n in at.number_input if n.label == "직접입력(%)"][0]
    num.set_value(42.5).run()
    slider = [s for s in at.slider if s.label == "살(BUY) 비율 (%)"][0]
    assert slider.value == 42.5
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["살(BUY) 비율"] == "42.50%"


def test_squad_size_default_11_blocks_12th_addition():
    at = AppTest.from_file(APP_PATH, default_timeout=60).run()
    tickers = ["VOO", "SPY", "IVV", "QQQ", "QQQM", "VTI", "DIA", "IWM",
              "TQQQ", "SOXX", "SOXL"]  # 검색 기본 시드 상위 11개 (SHOWN=8 한도 감안해 검색으로 개별 추가)
    for t in tickers:
        box = [w for w in at.text_input if w.label == "검색어"][0]
        box.set_value(t).run()
        btn = [b for b in at.button if b.label == "검색"][0]
        btn.click().run()
        add = [b for b in at.button if b.label.startswith(f"＋ {t} —")][0]
        add.click().run()
    assert not at.exception
    assert len([b for b in at.button if b.label.startswith("● ") or b.label.startswith("○ ")]) == 11

    box = [w for w in at.text_input if w.label == "검색어"][0]
    box.set_value("TLT").run()
    btn = [b for b in at.button if b.label == "검색"][0]
    btn.click().run()
    add = [b for b in at.button if b.label.startswith("＋ TLT —")][0]
    add.click().run()
    warnings = [w.value for w in at.warning]
    assert any("11" in w for w in warnings), warnings


def test_quantity_input_back_calculates_weight_with_real_price():
    """'몇 주 살까?' 에 주수를 넣으면 살(BUY) 비율이 역산되고, 실제 계산된 보유 주식 수가
    입력한 주수와 정확히 일치해야 한다 (반올림으로 1주 모자라던 버그의 회귀 테스트).

    입력칸은 커스텀 컴포넌트라 타이핑을 재현할 수 없으므로, 컴포넌트가 서버로 보내는
    값을 session_state 에 그대로 넣어 같은 경로를 태웁니다.
    """
    at = AppTest.from_file(APP_PATH, default_timeout=60).run()
    at = _add_qqq(at)

    sec_id = at.session_state["portfolio"].securities[0].id
    at.session_state[f"buy_{sec_id}"] = {"source": "qty", "amount": 0, "qty": 20, "nonce": 1}
    at.run()
    assert not at.exception

    slider = [s for s in at.slider if s.label == "살(BUY) 비율 (%)"][0]
    assert slider.value > 0.0

    metrics = {m.label: m.value for m in at.metric}
    assert metrics["보유 주식 수"] == "20"


def test_squad_size_toggle_allows_expanding_beyond_11():
    at = AppTest.from_file(APP_PATH, default_timeout=60).run()
    toggle = [t for t in at.toggle if "종목 더 담기" in t.label][0]
    assert toggle.value is False
    toggle.set_value(True).run()
    assert not at.exception
    # 세션의 Portfolio 객체에 바로 반영되는지도 확인
    assert at.session_state["portfolio"].max_squad_size == 26
