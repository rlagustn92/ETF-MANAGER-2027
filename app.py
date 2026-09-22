"""
app.py  --  ETF MANAGER : 화면(Streamlit) 진입점
===============================================

이 파일은 "화면 조립" 만 담당합니다. 계산은 services/, 데이터는 data/providers/ 에 있습니다.
(인수인계서 98, 107-1 : UI 와 계산/데이터 분리)

실행:  streamlit run app.py
연도 변경:  config.py 의 APP_YEAR 한 줄 (인수인계서 3, 116)

화면 구성 메모 (사용자 피드백 반영)
----------------------------------
- 금액 입력(초기자본 등)은 항상 세자리 콤마로 표시됩니다 -> money_input() 참고.
- 종목 목표비중은 "선택 종목 상세" 패널의 슬라이더가 유일한 편집 지점입니다.
  이 위젯들은 반드시 portfolio_service.compute() 호출 "이전"에 실행되어야
  이번 렌더에 바로 반영됩니다. 그래서 오른쪽 컬럼을 compute() 앞/뒤로 두 번 나눠서 씁니다
  (Phase A: 편집 위젯, Phase B: 계산 결과 표시). Streamlit 은 같은 컬럼에 여러 번
  with col_right: 를 써도 화면에는 순서대로 이어붙습니다.
- 위쪽 "간략 요약 바"는 전술판보다 먼저 화면에 자리를 예약(st.container())해 두고,
  compute() 결과가 나온 뒤에 채웁니다 -- 그래야 값은 최신인데 위치는 맨 위에 유지됩니다.
"""

from __future__ import annotations

import html
import re
from datetime import date

import pandas as pd
import streamlit as st

import config
import pitch_grid
import pitch_kit
import presets
from formatting import native_amt, pct, won, won_short
from components.buy_input import buy_input
from components.football_pitch import football_pitch
from components.local_store import local_store
from components.table_capture import table_capture
from data.providers import cache
from data.providers import search_provider
from models import numbers
from models.portfolio import Portfolio
from models.security import (
    DIST_METHOD_AUTO,
    DIST_METHOD_MANUAL,
    MARKET_KR,
    Security,
)
from services import (
    backtest_service,
    calculation_service,
    calendar_service,
    compare_service,
    composition_service,
    formation_service,
    naver_link_service,
    overlap_service,
    fx_service,
    portfolio_service,
    share_service,
    slot_service,
    tactic_service,
    visitor_service,
)
from services.portfolio_service import resolve_price
import ui_theme

st.set_page_config(page_title=config.app_name(), page_icon="⚽", layout="wide")
ui_theme.inject()


# =====================================================================
# 세션 상태
# =====================================================================
def _init_state() -> None:
    if "portfolio" not in st.session_state:
        st.session_state.portfolio = Portfolio(
            name="새 전술", initial_capital_krw=config.DEFAULT_INITIAL_CAPITAL_KRW)
    st.session_state.setdefault("selected_id", None)
    st.session_state.setdefault("search_results", [])
    st.session_state.setdefault("last_upload_sig", None)
    # 전술 슬롯. 브라우저에 저장된 게 있으면 바로 아래에서 덮어씁니다.
    if "slots" not in st.session_state:
        st.session_state["slots"] = [
            slot_service.slot_from_portfolio(st.session_state.portfolio)]
        st.session_state["slot_active"] = 0


def _reset_widgets_on_load() -> None:
    """새 전술을 불러왔을 때, 그 전술의 값으로 재초기화가 필요한 위젯들을 리셋."""
    for k in ("money_initial_capital", "money_bt_capital",
              "squad_full_toggle", "allow_overbudget_toggle"):
        st.session_state.pop(k, None)


_init_state()

# =====================================================================
# 브라우저에 저장해 둔 전술 복원
# =====================================================================
# ⚠ 이 블록은 반드시 **위젯이 하나라도 만들어지기 전**이어야 합니다.
#    위젯이 생긴 뒤에 그 위젯의 session_state 를 고치면 Streamlit 이
#    StreamlitWidgetAlreadyInstantiatedError 를 냅니다.
#
# 첫 렌더에는 None 이 옵니다(브라우저가 아직 답하기 전). 답이 오면 그때 복원하고
# 한 번 다시 그립니다. 저장된 게 없으면 다시 그리지 않으므로 헛일이 없습니다.
_restored = local_store(mode="read", key="ls_read")
if _restored and not st.session_state.get("store_read_done"):
    st.session_state["store_read_done"] = True
    # 저장이 실제로 되는 브라우저인지. 안 되면 아래에서 안내 문구가 달라집니다.
    st.session_state["store_writable"] = bool(_restored.get("writable", True))
    _saved = slot_service.loads(_restored.get("data"))
    if _saved.slots:
        st.session_state["slots"] = _saved.slots
        st.session_state["slot_active"] = _saved.active
        # 목표는 전술이 아니라 **사람의 것**이라 슬롯과 따로 복원합니다.
        st.session_state["goal_monthly_krw"] = _saved.goal_monthly_krw
        st.session_state.portfolio = _saved.slots[_saved.active].to_portfolio()
        st.session_state["selected_id"] = None
        _reset_widgets_on_load()
        st.rerun()

P: Portfolio = st.session_state.portfolio
FULL_SQUAD = len(pitch_grid.all_slots())  # 전술판 전체 슬롯 수 (인수인계서 확장 요청 반영)


# =====================================================================
# 표시/입력 헬퍼
# =====================================================================
# 숫자 표기(won / pct / won_short / native_amt)는 formatting.py 로 옮겼습니다.
# app.py 는 Streamlit 실행 파일이라 그냥 import 할 수 없어서 테스트를 붙일 수가
# 없는데, 돈을 잘못 적으면 사용자가 그대로 오해하는 부분이라 따로 뗐습니다.
def comment_text(comp) -> str:
    """커뮤니티 댓글에 그대로 붙여넣을 수 있는 글자 요약 (사용자 요청).

    📸 캡처는 이미지라, 네이버 댓글처럼 **이미지가 아예 안 되는 곳**에서는 못 씁니다.
    거기서도 포트폴리오를 보여줄 수 있게 같은 내용을 글자로 냅니다.

    캡처 이미지와 **같은 숫자, 같은 순서**여야 합니다. 둘이 다르면 같은 포트폴리오를
    두 군데에 올렸을 때 숫자가 어긋나 보입니다.
    """
    lines = [
        f"[{config.app_name()}] {P.name or '내 배당 포트폴리오'}",
        f"총 원금 {won_short(comp.total_actual_investment_krw)}"
        f" · 월평균 분배금 {won_short(comp.monthly_distribution_krw)}"
        f" · 연 {won_short(comp.annual_distribution_krw)}"
        f" (투자금 대비 분배율 {pct(comp.income_yield_on_invested_pct)})",
        f"※ 세전 · 최근 12개월 분배금 기준 · {config.today_local():%Y-%m-%d}",
        "",
    ]
    for r in sorted(comp.rows, key=lambda r: -r.security.target_weight):
        s = r.security
        name = (f"{s.display_name} ({s.ticker})" if s.market == MARKET_KR
                else (s.ticker or s.display_name))
        lines.append(f"· {name} {pct(s.target_weight * 100)}"
                     f" · {won_short(r.actual_investment_krw)}"
                     f" · 월 {won_short(r.monthly_distribution_krw)}")
    # 이 포트폴리오를 그대로 여는 주소. **이 앱에서 사람을 데려오는 유일한 통로**입니다.
    # 캡처 이미지에는 링크를 걸 수 없으니(그림 속 글자는 못 누릅니다), 댓글에 같이
    # 붙는 이 글자가 실제 유입 경로가 됩니다.
    lines += ["", "▶ 이 전술 그대로 열어보기", share_service.share_url(P)]
    return "\n".join(lines)


def composition_bars(comp) -> None:
    """내가 뭘 담았는지 가로 막대 세 줄로 (사용자 요청).

    왜 도넛이 아니라 막대인가
    -------------------------
    폰에서 도넛 세 개를 나란히 놓으면 각각 100px 도 안 됩니다. 거기에
    "커버드콜 68%" 라는 글자가 안 들어갑니다. 막대는 글자를 **안에** 넣을 수 있고
    좁아져도 그대로 읽힙니다.
    """
    bars = composition_service.bars(comp)
    if not bars:
        return
    # 한 막대 안에서만 진하기로 순서를 표현합니다. 색으로 좋고 나쁨을 말하지
    # 않습니다 -- 색이 곧 추천이 되면 안 됩니다.
    shades = ["#1F6B47", "#4E9E78", "#8FBFA6", "#BFD6C9", "#DCE6E0"]
    html_parts = []
    for bar in bars:
        cells = "".join(
            f"<b style='width:{s.pct:.4f}%;background:{shades[min(i, len(shades) - 1)]};"
            f"color:{'#fff' if i < 2 else '#12263c'}'>"
            f"{html.escape(s.label)} {s.pct:.0f}%</b>"
            for i, s in enumerate(bar.slices)
        )
        html_parts.append(
            f"<div class='comp-row'><div class='comp-title'>{html.escape(bar.title)}</div>"
            f"<div class='comp-stack'>{cells}</div></div>"
        )
    st.markdown("<div class='comp-wrap'>" + "".join(html_parts) + "</div>",
                unsafe_allow_html=True)

    verdict = composition_service.tilt(comp)
    if verdict:
        label, why = verdict
        # 평가가 아니라 거울입니다. 왜 그렇게 봤는지를 반드시 같이 적습니다.
        st.markdown(
            f"<div class='comp-tilt'>지금 구성은 <b>{html.escape(label)}</b> "
            f"<span class='why'>{html.escape(why)}</span></div>",
            unsafe_allow_html=True,
        )


def dialog_note(html_text: str) -> None:
    """떠 있는 창 안의 설명 한 줄.

    st.caption 은 아주 옅은 잉크(--ink-tertiary)라 흰 모달 위에서 거의 안 읽힙니다.
    창 안의 설명은 "그냥 참고" 가 아니라 **그 표를 어떻게 읽어야 하는지** 를 말하는
    것이라, 한 단계 진한 잉크로 씁니다.
    """
    st.markdown(f"<div class='dlg-note'>{html_text}</div>", unsafe_allow_html=True)


def note(html_text: str) -> None:
    """그냥 지나치면 숫자를 오해하게 되는 설명 (ui_theme 의 .note).

    일반 캡션보다 눈에 띄게 표시합니다. <b> 강조만 쓰고, 넣는 값은 앱이 만든
    숫자 문자열이어야 합니다 (외부에서 온 문자열을 그대로 넣지 마세요).
    """
    st.markdown(f"<div class='note'>{html_text}</div>", unsafe_allow_html=True)


def is_admin() -> bool:
    """관리자(= 앱 주인)인지. 캐시 비우기 같은 '전체에 영향 주는' 기능을 가립니다.

    주소 뒤에 ?admin=<키> 를 붙였을 때만 True. 키는 secrets 의 ADMIN_KEY 와 비교합니다.
    ADMIN_KEY 를 설정하지 않으면(개인 PC 에서 혼자 쓸 때) 항상 관리자로 봅니다.
    로그인 기능이 아니라 "남들이 실수로 누르지 못하게" 하는 정도의 가림막입니다.
    """
    try:
        expected = str(st.secrets.get("ADMIN_KEY", "") or "")
    except Exception:
        expected = ""
    if not expected:
        return True                      # 키 미설정 = 개인용 실행
    return st.query_params.get("admin") == expected


def summary_strip(cells: list[tuple[str, str, bool]]) -> None:
    """전술판 위쪽 한 줄 요약. (라벨, 값, 빨갛게 표시할지) 목록을 한 칸짜리 박스로 그립니다.

    "·" 로 길게 이어 쓰면 장황해서, 라벨 위/숫자 아래로 끊어 읽히게 했습니다 (사용자 요청).
    """
    inner = "".join(
        f"<div class='cell'><div class='k'>{html.escape(k)}</div>"
        f"<div class='v{' neg' if neg else ''}'>{html.escape(v)}</div></div>"
        for k, v, neg in cells
    )
    st.markdown(f"<div class='stat-strip'>{inner}</div>", unsafe_allow_html=True)


def money_input(label: str, key: str, default_value: float, min_value: float = 0.0,
                help: str | None = None) -> float:
    """세자리 콤마(,)가 항상 표시되는 금액 입력 위젯.

    Streamlit 의 number_input 은 원화 같은 큰 정수 금액에도 콤마를 표시하지 못해서
    (예: 100000000) text_input + 자동 서식화로 구현합니다.
    """
    if key not in st.session_state:
        st.session_state[key] = f"{int(default_value):,}"

    def _normalize() -> None:
        digits = re.sub(r"[^\d]", "", st.session_state.get(key, ""))
        val = max(int(min_value), int(digits) if digits else 0)
        st.session_state[key] = f"{val:,}"

    st.text_input(label, key=key, on_change=_normalize, help=help)
    digits = re.sub(r"[^\d]", "", st.session_state.get(key, ""))
    return float(max(int(min_value), int(digits) if digits else 0))


def _apply_preset(preset: presets.Preset) -> None:
    """예시 구성(또는 초기화)을 현재 전술로 교체. 기존에 담긴 종목은 사라집니다."""
    new_portfolio = presets.build_portfolio(preset)
    st.session_state.portfolio = new_portfolio
    st.session_state.selected_id = (new_portfolio.securities[0].id
                                    if new_portfolio.securities else None)
    st.session_state.pop("preset_pending", None)
    for _k in ("bt_result", "bt_signature", "bt_context"):
        st.session_state.pop(_k, None)
    _reset_widgets_on_load()   # 시드 입력칸 등을 새 값으로 다시 채우기 위해


def _live_name() -> str:
    """지금 전술명.

    ⚠ 전술명 입력칸에 key 를 붙이고 session_state 로 읽으면 안 됩니다.
      key 가 붙은 text_input 은 **예시를 불러와도 입력칸 글자가 안 바뀝니다**
      (브라우저가 들고 있던 옛 값을 계속 돌려줍니다). 그러면 다음 클릭 때 옛 이름이
      되돌아와서 슬롯 이름을 덮어씁니다. 실제로 겪은 버그입니다.
      key 없이 value= 로만 그려야 값이 갱신되고, 그래서 여기서는 P.name 만 봅니다.
      대신 슬롯 바를 전술명 입력칸보다 **나중에** 그려서 이름이 안 밀리게 합니다.
    """
    return str(P.name or slot_service.DEFAULT_SLOT_NAME)


def _current_slot() -> slot_service.Slot:
    """지금 편집 중인 내용을 슬롯 한 칸으로."""
    portfolio_dict = P.to_dict()
    portfolio_dict["name"] = _live_name()
    return slot_service.Slot(name=_live_name(), tactic=portfolio_dict)


def _slots_snapshot() -> tuple[list[slot_service.Slot], int]:
    """저장/내려받기용. 지금 편집 중인 칸만 최신 내용으로 갈아끼웁니다."""
    slots = list(st.session_state["slots"])
    active = int(st.session_state["slot_active"])
    if 0 <= active < len(slots):
        slots[active] = _current_slot()
    return slots, active


def _open_slot(slots: list[slot_service.Slot], target: int) -> None:
    """슬롯 목록을 확정하고 target 번 칸을 펼칩니다."""
    target = max(0, min(target, len(slots) - 1))
    st.session_state["slots"] = slots
    st.session_state["slot_active"] = target
    st.session_state.portfolio = slots[target].to_portfolio()
    st.session_state["selected_id"] = None
    _dismiss_preset_confirm()
    for k in ("bt_result", "bt_signature", "bt_context"):
        st.session_state.pop(k, None)
    _reset_widgets_on_load()


def _switch_slot(target: int) -> None:
    """슬롯 이동. 지금 칸을 저장하고 저쪽 칸을 펼칩니다."""
    slots, active = _slots_snapshot()
    # 아무것도 안 담은 빈 칸은 떠날 때 치웁니다. 그래야 "＋" 를 눌러보다 만
    # 흔적이 탭으로 영영 남지 않습니다. (마지막 한 칸은 남겨둡니다)
    if len(slots) > 1 and active != target and not P.securities:
        slots.pop(active)
        if target > active:
            target -= 1
    _open_slot(slots, target)


def _add_slot() -> None:
    """빈 칸을 하나 더 만들고 그리로 갑니다.

    ⚠ 여기서는 _switch_slot 을 쓰면 안 됩니다. 지금 칸이 비어 있으면 그쪽이
    "떠날 때 빈 칸 치우기"를 해버려서, 빈 칸에서 ＋ 를 누르면 하나 지우고 하나
    만드는 꼴이 됩니다 -- 사용자 눈에는 **아무 일도 안 일어난 것**으로 보입니다.
    """
    slots, _ = _slots_snapshot()
    if len(slots) >= slot_service.MAX_SLOTS:
        return
    name = slot_service.unique_name(slots)
    slots.append(slot_service.Slot(
        name=name, tactic=slot_service.empty_portfolio(name).to_dict()))
    _open_slot(slots, len(slots) - 1)


def _apply_slots(new_slots: list[slot_service.Slot], *, replace_all: bool) -> None:
    """불러온 전술을 슬롯에 반영. 파일 한 개면 지금 칸만, 백업 ZIP 이면 전부."""
    if not new_slots:
        return
    if replace_all:
        st.session_state["slots"] = new_slots[:slot_service.MAX_SLOTS]
        st.session_state["slot_active"] = 0
    else:
        slots = list(st.session_state["slots"])
        active = int(st.session_state["slot_active"])
        if 0 <= active < len(slots):
            slots[active] = new_slots[0]
        else:
            slots, active = new_slots[:1], 0
        st.session_state["slots"] = slots
        st.session_state["slot_active"] = active
    active = int(st.session_state["slot_active"])
    st.session_state.portfolio = st.session_state["slots"][active].to_portfolio()
    st.session_state["selected_id"] = None
    for k in ("bt_result", "bt_signature", "bt_context"):
        st.session_state.pop(k, None)
    _reset_widgets_on_load()


def _adopt_shared(items: list[share_service.ShareItem]) -> None:
    """공유 링크로 받은 전술을 내 것으로 가져옵니다.

    ⚠ 자동으로 적용하면 안 됩니다. 링크를 눌러 들어온 사람이 이미 자기 전술을
      짜두었을 수 있는데, 그걸 말없이 덮어쓰면 남의 링크 하나로 남의 작업이
      날아갑니다. 그래서 배너의 버튼을 눌렀을 때만 여기로 옵니다.

    담을 자리도 비어 있는 칸을 먼저 찾습니다. 지금 칸에 뭔가 담겨 있으면 새 칸을
    만들어 그리로 넣습니다 -- 가져오기가 지우기가 되면 안 되니까요.
    """
    # 종목 이름을 찾느라 시간이 걸릴 수 있습니다(모르는 미국 티커는 조회해야 함).
    # 화면이 멈춘 것처럼 보이지 않게 돌아가는 표시를 띄웁니다.
    with st.spinner("전술을 가져오는 중..."):
        shared = share_service.to_portfolio(
            items, name="받은 전술", initial_capital_krw=P.initial_capital_krw)
    slots, active = _slots_snapshot()
    if not P.securities:
        slots[active] = slot_service.slot_from_portfolio(shared)
        target = active
    elif len(slots) < slot_service.MAX_SLOTS:
        slots.append(slot_service.slot_from_portfolio(shared))
        target = len(slots) - 1
    else:
        # 칸이 다 찼으면 지금 칸에 넣습니다. 이때는 덮어쓰는 것이므로 배너에서
        # 미리 알려줍니다.
        slots[active] = slot_service.slot_from_portfolio(shared)
        target = active
    _open_slot(slots, target)
    _clear_share_link()


def _clear_share_link() -> None:
    """주소창의 ?p= 를 지웁니다.

    안 지우면 새로고침할 때마다 "누군가 공유한 전술입니다" 가 다시 뜨고,
    이미 가져온 사람에게는 그게 잔소리가 됩니다.
    """
    st.session_state["share_dismissed"] = True
    try:
        if share_service.QUERY_KEY in st.query_params:
            del st.query_params[share_service.QUERY_KEY]
    except Exception:
        pass


def _backtest_signature(portfolio: Portfolio, start, capital, include_dist) -> tuple:
    """백테스트 결과가 "어떤 조건으로" 나온 것인지를 나타내는 지문.

    저장된 결과의 지문과 지금 화면의 지문이 다르면 그 결과는 낡은 것입니다.
    비교에 쓰는 값만 담고, 화면 배치(슬롯 위치)처럼 결과와 무관한 것은 뺍니다.
    """
    return (
        tuple(sorted((s.market, s.ticker, round(float(s.target_weight), 6))
                     for s in portfolio.securities)),
        round(numbers.safe_float(capital), 2),
        str(start),
        bool(include_dist),
        bool(portfolio.fractional_shares),
    )


def _dismiss_preset_confirm() -> None:
    """예시 불러오기 확인창("정말 바꿀래요?")을 닫습니다.

    확인창이 떠 있는데 사용자가 마음을 바꿔 다른 걸 하면(종목을 담거나, 지우거나,
    다른 종목을 고르면) 그건 "예시 불러오기는 됐다"는 뜻입니다. 그런데도 경고가
    화면 위쪽에 계속 남아 방해하고, **실수로 '네, 바꿀게요' 를 누르면 그동안
    작업하던 포트폴리오가 통째로 날아갑니다.**

    그래서 포트폴리오를 건드리는 동작이 일어나면 확인창을 조용히 닫습니다.
    (닫기만 할 뿐 아무것도 지우지 않으므로, 잘못 닫혀도 잃는 게 없습니다)
    """
    st.session_state.pop("preset_pending", None)


def _add_security(hit: search_provider.SearchHit) -> bool:
    """반환값이 False 면 실패(중복/한도 초과 등) -- 호출부는 이때 st.rerun() 을 하면 안 됩니다.
    rerun 을 하면 방금 띄운 st.warning() 메시지가 사용자에게 보이기도 전에 지워집니다."""
    # 슬롯 배치는 Portfolio.add() 가 자동으로 담당 (빈 슬롯 중 추정 라인에서 가장 가까운 곳)
    sec = Security(
        market=hit.market, ticker=hit.ticker, name=hit.name, display_name=hit.display_name,
        currency=hit.currency, asset_type=hit.asset_type, target_weight=0.0,
    )
    try:
        P.add(sec)
        st.session_state.selected_id = sec.id
        _dismiss_preset_confirm()
        return True
    except ValueError as e:
        st.warning(str(e))
        return False


# =====================================================================
# 헤더
# =====================================================================
tc1, tc2 = st.columns([3, 1])
with tc1:
    st.markdown(
        f"<h2 class='app-title'>{config.app_name_with_icon()}"
        f"<span class='app-version'>{config.app_version_label()}</span>"
        f"<a class='ext-link feedback' target='_blank' rel='noopener noreferrer' "
        f"href='{config.FEEDBACK_URL}'>{config.FEEDBACK_LABEL} ↗</a>"
        # 자매 서비스 두 개(고르는 곳 -> 관리하는 곳)는 한 덩어리로 묶습니다.
        # 문구가 길어서 그냥 두면 둘째 칩만 혼자 다음 줄로 떨어집니다. 묶어두면
        # 줄이 바뀌더라도 **둘이 나란히** 같이 내려가서 한 쌍으로 읽힙니다.
        f"<span class='sister-links'>"
        f"<a class='ext-link inside' target='_blank' rel='noopener noreferrer' "
        f"href='{config.INSIDE_URL}'>{config.INSIDE_LABEL} ↗</a>"
        f"<a class='ext-link paystub' target='_blank' rel='noopener noreferrer' "
        f"href='{config.PAYSTUB_URL}'>{config.PAYSTUB_LABEL} ↗</a>"
        f"</span></h2>",
        unsafe_allow_html=True,
    )
with tc2:
    # 방문자 수: 접속(세션) 1회당 1 만 올립니다. 화면이 다시 그려질 때마다 올리면
    # 숫자가 엉터리가 되므로, 이번 세션에 이미 셌는지를 session_state 로 확인합니다.
    if "visitor_counts" not in st.session_state:
        st.session_state["visitor_counts"] = visitor_service.count_visit()
    _counts = st.session_state["visitor_counts"]
    if _counts:
        _today, _total = _counts
        st.markdown(
            "<div class='visitors'>"
            f"<span><b>TODAY</b> {_today:,}</span>"
            f"<span><b>TOTAL</b> {_total:,}</span>"
            "</div>",
            unsafe_allow_html=True,
        )
# =====================================================================
# 전술 슬롯 (사용자 요청: 공격형/배당형처럼 여러 개를 굴리는 사람)
# =====================================================================
# 저장 칸이 하나뿐인 자동 저장은 포트폴리오를 여러 개 굴리는 사람에게 반쪽입니다.
# 지금 보고 있는 칸이 알아서 저장되고, 탭을 눌러 갈아탑니다.
#
# ⚠ 여기서는 자리만 잡아두고, 실제로 그리는 건 전술명 입력칸보다 **뒤**입니다.
#   슬롯 이름 = 전술명이라, 입력칸보다 먼저 그리면 이름이 한 박자 늦게 따라옵니다.
#   (요약 바도 같은 방식으로 자리를 먼저 잡습니다)
slot_bar_slot = st.container()

# 공유 링크로 들어온 사람에게 보일 배너 자리. 링크를 누른 사람이 **제일 먼저**
# 봐야 하는 것이라 맨 위에 둡니다. (내용은 아래에서 채웁니다)
share_banner_slot = st.container()

hc1, hc2, hc3 = st.columns([2, 1, 1])
with hc1:
    # 이름 추천 버튼이 넣어둔 값을 위젯을 만들기 **전에** 반영합니다.
    # (만들어진 뒤에 고치면 StreamlitWidgetAlreadyInstantiatedError)
    _suggested = st.session_state.pop("pending_tactic_name", None)
    if _suggested:
        P.name = _suggested
    P.name = st.text_input("전술명", value=P.name, placeholder="전술명")

    # ---- 예시로 시작하기 (사용자 요청) ----------------------------------------
    # 빈 화면에서 뭘 담아야 할지 막막하지 않도록, 버튼 한 번으로 채워지는 예시 3종.
    # 전술명 아래 남는 자리에 가로로 놓아 헤더 높이를 늘리지 않습니다.
    # 담긴 종목을 덮어쓰는 동작이라, 이미 담은 게 있으면 한 번 더 확인받습니다.
    # 윗줄 = 성향별(안정/보통/공격), 아랫줄 = 목표 금액별 + 초기화.
    # 한 줄에 6개를 넣으면 버튼 글자가 잘려서 두 줄로 나눴습니다.
    st.caption("처음이라면 예시로 시작해보세요 · 예시일 뿐이며 투자 추천이 아닙니다.")
    for _row in (presets.PRESETS[:3], presets.PRESETS[3:] + (presets.RESET,)):
        for _col, _preset in zip(st.columns(len(_row)), _row):
            _clicked = _col.button(_preset.label, key=f"preset_{_preset.key}",
                                   width="stretch", help=_preset.summary)
            # 버튼 글자만으로는 뭘 받게 되는지 모릅니다. 특히 **시드가 바뀐다는 것**을
            # 누르고 나서야 알게 되므로, 누르기 전에 밑에 한 줄로 적어둡니다.
            _col.caption(_preset.chip())
            if _clicked:
                if P.securities:
                    st.session_state["preset_pending"] = _preset.key
                else:
                    _apply_preset(_preset)
                st.rerun()

    _pending = presets.get(st.session_state.get("preset_pending") or "")
    if _pending:
        # 무엇이 사라지는지만 말하지 말고 **무엇이 들어오는지**도 말합니다.
        # 특히 시드가 바뀐다는 건 지금까지 누르고 나서야 알 수 있었습니다.
        if _pending is presets.RESET:
            _confirm = f"지금 담은 종목 {len(P.securities)}개가 모두 지워집니다."
        else:
            _confirm = (f"'{_pending.label}' 예시를 불러오면 지금 담은 종목 "
                        f"{len(P.securities)}개가 지워지고 "
                        f"{len(_pending.items)}종목으로 바뀝니다.")
            if abs(P.initial_capital_krw - _pending.capital_krw) > 0.5:
                _confirm += (f" 내 시드도 {won_short(P.initial_capital_krw)} → "
                             f"{won_short(_pending.capital_krw)} 로 바뀝니다.")
        st.warning(_confirm)
        _yc, _nc = st.columns(2)
        if _yc.button("네, 바꿀게요", key="preset_ok", width="stretch", type="primary"):
            _apply_preset(_pending)
            st.rerun()
        if _nc.button("취소", key="preset_cancel", width="stretch"):
            st.session_state.pop("preset_pending", None)
            st.rerun()
with hc2:
    P.initial_capital_krw = money_input(
        "내 시드 (₩)", key="money_initial_capital", default_value=P.initial_capital_krw,
        min_value=0, help="숫자만 입력하면 자동으로 콤마(,)가 표시됩니다.",
    )
with hc3:
    st.markdown("<div style='height:1.7rem'></div>", unsafe_allow_html=True)  # 라벨 한 줄만큼 높이 맞춤
    P.fractional_shares = st.toggle("소수점까지 사기", value=P.fractional_shares,
                                    help="기본값 OFF. 켜면 소수점 주식 수량을 허용합니다.")
    if "squad_full_toggle" not in st.session_state:
        st.session_state["squad_full_toggle"] = P.max_squad_size >= FULL_SQUAD
    full_squad = st.toggle(
        f"종목 더 담기 (최대 {FULL_SQUAD}개)", key="squad_full_toggle",
        help=(f"기본은 축구 한 팀처럼 {config.SQUAD_SIZE_DEFAULT}종목까지만 담을 수 있어요. "
             f"켜면 전술판 슬롯 전체({FULL_SQUAD}개)까지 늘어납니다."),
    )
    P.max_squad_size = FULL_SQUAD if full_squad else config.SQUAD_SIZE_DEFAULT
    # 26개를 담은 채로 토글을 끄면 "보유 26개 / 한도 11개" 라는 모순이 생깁니다.
    # 담은 종목을 강제로 지우거나 토글을 못 끄게 막지는 않습니다(하려는 걸 막기보다
    # 알려주는 쪽). 다만 아무 말도 안 하면 나중에 종목을 추가하려다 거부당하고서야
    # "왜 더 못 담지?" 하게 되므로, 지금 상태를 분명히 적어둡니다.
    if len(P.securities) > P.max_squad_size:
        st.caption(f"⚠ 지금 {len(P.securities)}개를 담고 있어 한도({P.max_squad_size}개)를 "
                   f"넘습니다. 담은 종목은 그대로 두지만, 더 담으려면 이 토글을 다시 켜세요.")
    if "allow_overbudget_toggle" not in st.session_state:
        st.session_state["allow_overbudget_toggle"] = not P.strict_capital_limit
    allow_over = st.toggle(
        "시드보다 더 담기 허용", key="allow_overbudget_toggle",
        help="기본값 OFF: 종목 살(BUY) 비율 합계가 내 시드(100%)를 넘지 않도록 자동으로 "
             "잘라냅니다. 켜면 제한 없이 입력할 수 있고, 초과 시 경고만 표시합니다.",
    )
    P.strict_capital_limit = not allow_over

# ---- 공유 링크로 들어온 사람에게 보이는 배너 -------------------------------
# 링크를 누른 사람은 "남의 전술"을 들고 온 상태입니다. 그대로 적용하지 않고
# 무엇을 받게 되는지 먼저 보여준 뒤, 누를 때만 가져옵니다.
_shared_items = ([] if st.session_state.get("share_dismissed")
                 else share_service.decode(st.query_params.get(share_service.QUERY_KEY)))
if _shared_items:
    _full = len(st.session_state["slots"]) >= slot_service.MAX_SLOTS and P.securities
    with share_banner_slot, st.container(border=True):
        _sc1, _sc2, _sc3 = st.columns([3, 1, 0.7])
        with _sc1:
            st.markdown(f"**누군가 공유한 전술입니다** — {share_service.summary(_shared_items)}")
            st.caption("내 시드에 맞춰 다시 계산됩니다. "
                       + ("⚠ 슬롯이 다 차서 **지금 칸을 덮어씁니다.**" if _full
                          else "지금 담은 종목은 그대로 두고 새 칸에 담습니다."))
        if _sc2.button("이 전술 따라하기", type="primary", width="stretch",
                       key="share_adopt"):
            _adopt_shared(_shared_items)
            st.rerun()
        if _sc3.button("닫기", width="stretch", key="share_dismiss"):
            _clear_share_link()
            st.rerun()

# ---- 슬롯 바 (위에서 자리만 잡아둔 곳에 그립니다) --------------------------
# 전술명 입력칸이 먼저 돌아야 슬롯 이름이 바로 따라옵니다. 그래서 화면에서는
# 위에 있지만 코드로는 여기서 그립니다.
with slot_bar_slot:
    _slots: list[slot_service.Slot] = st.session_state["slots"]
    _active: int = int(st.session_state["slot_active"])
    sb_left, sb_right = st.columns([2.6, 1])
    with sb_left:
        # 칸 수를 MAX_SLOTS+1 로 고정합니다. 슬롯이 늘 때마다 버튼 너비가 출렁이면
        # 방금 누른 자리에 다른 버튼이 와 있게 됩니다.
        _cols = st.columns(slot_service.MAX_SLOTS + 1)
        for _i, _slot in enumerate(_slots):
            _nm = _live_name() if _i == _active else _slot.name
            _cnt = len(P.securities) if _i == _active else _slot.security_count
            if _cols[_i].button(
                    slot_service.slot_label(_nm, _cnt), key=f"slot_{_i}", width="stretch",
                    type="primary" if _i == _active else "secondary",
                    help=f"{_nm} · 종목 {_cnt}개"):
                if _i != _active:
                    _switch_slot(_i)
                    st.rerun()
        if len(_slots) < slot_service.MAX_SLOTS:
            if _cols[len(_slots)].button("＋ 빈 칸", key="slot_add", width="stretch",
                                         help="전술을 하나 더 만듭니다. "
                                              "빈 채로 다른 칸으로 가면 저절로 치워집니다."):
                _add_slot()
                st.rerun()
    with sb_right:
        _zip_slots, _ = _slots_snapshot()
        st.download_button(
            f"💾 전술 {len(_zip_slots)}개 한 번에 저장", data=slot_service.to_zip(_zip_slots),
            file_name=slot_service.zip_filename(len(_zip_slots)), mime="application/zip",
            width="stretch",
            help="슬롯 전부를 ZIP 파일 하나로 내려받습니다. 압축을 풀면 전술마다 "
                 "JSON 파일이 하나씩 나오고, 이 ZIP 을 그대로 다시 올리면 슬롯이 "
                 "이름까지 한 번에 복원됩니다.",
        )

    # ---- 두 전술 나란히 비교 (슬롯이 2개 이상일 때만) ----------------------
    # 지금 보고 있는 칸이 A, 여기서 고르는 게 B 입니다. 슬롯 두 개를 고르는
    # "선택 모드" 를 만들면 클릭이 늘고 헷갈립니다 -- 지금 보고 있는 게 A 라는 건
    # 설명이 필요 없습니다.
    # 슬롯은 많아야 3칸이라 고를 게 한둘뿐입니다. 드롭다운은 과한 장치였고
    # (열어서 고르는 두 번의 동작, 게다가 검색 필터 때문에 항목이 가려지기도 합니다),
    # **버튼이 더 눈에 띄고 한 번에 끝납니다.**
    _other_slots = [(i, s) for i, s in enumerate(_slots) if i != _active]
    for _oi, _oslot in _other_slots:
        if sb_right.button(compare_service.button_label(_oslot.name),
                           key=f"cmp_{_oi}", width="stretch",
                           help=f"지금 보는 전술과 '{_oslot.name}' 을 나란히 놓고 봅니다."):
            st.session_state["cmp_target"] = _oi
            st.session_state["cmp_open"] = True
            st.rerun()

    # 저장이 되는 브라우저인지에 따라 안내가 달라집니다. 늘 같은 경고문만 띄워두면
    # 아무도 안 읽는데, 진짜 저장이 안 되는 순간에만 말이 달라지면 눈에 들어옵니다.
    if (st.session_state.get("store_read_done")
            and not st.session_state.get("store_writable", True)):
        st.warning("⚠ **이 브라우저에서는 저장이 안 됩니다.** 시크릿 모드이거나 저장소가 "
                   "막혀 있어요. 남기시려면 아래 **전술 저장**으로 파일을 받아두세요.")
    else:
        st.caption("자동 저장됨 · **이 브라우저에만** 저장됩니다. 다른 기기나 시크릿 "
                   "모드에서는 안 보여요. 남기시려면 파일로 받아두세요.")

# 전술 파일을 불러오면서 고친 값이 있으면 여기서 알립니다.
# (불러오기 직후에는 st.rerun() 이 메시지를 지우므로 세션에 넣어뒀다가 꺼냅니다)
_load_note = st.session_state.pop("tactic_load_note", None)
if _load_note:
    st.info(_load_note)

# 위쪽 "간략 요약 바" 자리 예약 -- 값은 compute() 이후에 채움 (아래쪽 "상세" 요약과 분리)
summary_bar_slot = st.container()
st.write("")

# =====================================================================
# 본문: 좌(검색·보유종목) / 중(전술판) / 우(선택 종목 상세)
# =====================================================================
col_left, col_mid, col_right = st.columns(
    [1.05, config.PITCH_MID_COL_RATIO, 1.15], gap="small",
)

# ---- 좌 (1): 보유 종목 -- 추가 즉시 여기 보이도록 검색보다 위에 배치 ----------
with col_left:
    st.markdown("#### 내가 담은 종목")
    if not P.securities:
        st.caption("아래에서 검색해 종목을 추가하세요.")
    for sec in P.securities:
        label = sec.display_name if sec.market == MARKET_KR else sec.ticker
        mark = "●" if sec.id == st.session_state.selected_id else "○"
        if st.button(f"{mark} {label} · {sec.target_weight * 100:.2f}%",
                     key=f"pick_{sec.id}", width="stretch"):
            st.session_state.selected_id = sec.id
            _dismiss_preset_confirm()
            st.rerun()
    st.caption("클릭하면 오른쪽 상세 패널에서 비중을 바로 설정할 수 있습니다.")

    st.divider()
    st.markdown("#### 종목 검색")
    # 뭘 검색할지부터 막히는 사람이 제일 많습니다. 검색칸 바로 위에서 종목 고르는
    # 서비스로 보내줍니다.
    st.markdown(
        f"<a class='ext-link inside block' target='_blank' rel='noopener noreferrer' "
        f"href='{config.INSIDE_URL}'>{config.INSIDE_LABEL} ↗</a>",
        unsafe_allow_html=True,
    )
    q = st.text_input("검색어", placeholder="QQQ / 삼성전자 / 005930",
                      label_visibility="collapsed")
    mkt = st.radio("시장", ["전체", "미국", "한국"], horizontal=True, label_visibility="collapsed")
    if st.button("검색", width="stretch"):
        mf = {"전체": "ALL", "미국": "US", "한국": "KR"}[mkt]
        with st.spinner("검색 중..."):
            try:
                st.session_state.search_results = search_provider.search(q, mf, limit=25)
            except Exception as e:  # 검색 실패가 앱을 죽이지 않음
                st.session_state.search_results = []
                st.error(f"검색 실패: {e}")

    results = st.session_state.search_results
    SHOWN = 8
    for hit in results[:SHOWN]:
        if st.button(f"＋ {hit.label()}", key=f"add_{hit.market}_{hit.ticker}",
                     width="stretch"):
            if _add_security(hit):
                st.rerun()
    if len(results) > SHOWN:
        with st.expander(f"더 보기 ({len(results) - SHOWN}개)"):
            for hit in results[SHOWN:]:
                if st.button(f"＋ {hit.label()}", key=f"more_{hit.market}_{hit.ticker}",
                             width="stretch"):
                    if _add_security(hit):
                        st.rerun()

# ---- sel: 현재 선택된 종목 ------------------------------------------------
sel = P.get(st.session_state.selected_id) if st.session_state.selected_id else None

# ---- 우 (Phase A): 선택 종목 편집 -- compute() 전에 실행해야 이번 렌더에 반영됨 ----
with col_right:
    st.markdown("#### 이 종목 자세히 보기")
    if sel is None:
        st.caption("왼쪽 목록이나 전술판에서 카드를 클릭하세요.")
    else:
        # 티커만 보고는 무슨 종목인지 모를 수 있어서(예: "O" = Realty Income),
        # 전체 이름과 증권 사이트 바로가기를 함께 보여줍니다 (사용자 요청).
        #
        # 네이버는 주소를 확인하지 못하면 None 이 옵니다. 그럴 때는 링크를 아예 안
        # 그립니다 — 지어낸 주소로 보내면 사용자가 빈 페이지를 보게 됩니다.
        # 칩 셋을 한 덩어리(ext-links)로 묶습니다. 안 묶으면 종목명 길이에 따라
        # 마지막 칩만 혼자 다음 줄로 떨어져 나갑니다(SCHD 에서 실제로 그랬습니다).
        _naver = naver_link_service.naver_url(sel.market, sel.ticker)
        _links = (
            f"<a class='ext-link' target='_blank' rel='noopener noreferrer' "
            f"href='{presets.toss_invest_url(sel.market, sel.ticker)}'>토스 ↗</a> "
            f"<a class='ext-link' target='_blank' rel='noopener noreferrer' "
            f"href='{presets.yahoo_finance_url(sel.market, sel.ticker)}'>야후 ↗</a>"
        )
        if _naver:
            _links += (f" <a class='ext-link' target='_blank' rel='noopener noreferrer' "
                       f"href='{html.escape(_naver, quote=True)}'>네이버 ↗</a>")
        st.markdown(
            f"**{html.escape(sel.display_name)}**  ·  `{html.escape(sel.ticker)}`  "
            f"<span class='ext-links'>{_links}</span>",
            unsafe_allow_html=True,
        )
        _full_name = sel.name or ""
        st.caption(
            (f"{_full_name} · " if _full_name and _full_name != sel.display_name else "")
            + f"{'한국' if sel.market == MARKET_KR else '미국'} · {sel.currency} · {sel.asset_type}"
        )

        # 전술판 이름표. 한국 ETF 는 이름이 길어서 자동으로 줄여 쓰는데(pitch_kit),
        # 단어 사전 기반이라 새로 상장한 상품은 못 줄이거나 결과가 어색할 수 있습니다.
        # 그래서 직접 고칠 길을 열어 둡니다. 비우면 다시 자동으로 돌아갑니다.
        # 정식 이름은 위 제목과 캡처 이미지의 종목 명단에 그대로 남습니다.
        _auto_label = pitch_kit.card_label(sel.market, sel.ticker, sel.display_name)
        _typed = st.text_input(
            "전술판 이름표", value=sel.card_label, key=f"lbl_{sel.id}",
            placeholder=_auto_label, max_chars=20,
            help="유니폼 아래에 찍히는 글자입니다. 비워두면 정식 이름을 자동으로 줄여서 씁니다.",
        )
        # 줄바꿈/탭이 섞이면(불러온 JSON 등) 이름표에서 글자가 사라진 것처럼 보이므로 한 칸으로 정리.
        sel.card_label = re.sub(r"\s+", " ", _typed or "").strip()

        slider_key, num_key = f"wsel_{sel.id}", f"wsel_num_{sel.id}"
        if slider_key not in st.session_state:
            st.session_state[slider_key] = round(sel.target_weight * 100, 2)
        if num_key not in st.session_state:
            st.session_state[num_key] = st.session_state[slider_key]

        def _apply_clamped_weight(pct_value: float) -> None:
            """목표비중 편집값을 정책(Portfolio.clamp_weight_pct)에 맞게 보정해 저장.

            strict_capital_limit(기본 ON) 이면 다른 종목들과의 합계가 100% 를 넘지
            않도록 자동으로 잘라내고, 잘렸으면 경고 메시지를 세션에 남깁니다
            (사용자 요청: 초기자본 초과를 기본값으로 막고, 토글로 껐다 켤 수 있게).
            """
            clamped, was_clamped = P.clamp_weight_pct(sel.id, pct_value)
            st.session_state[slider_key] = clamped
            st.session_state[num_key] = clamped
            st.session_state["weight_clamp_warning"] = (
                f"⚠ 살(BUY) 비율이 내 시드 한도까지(다른 종목 제외 여유 {clamped:.2f}%)로 "
                f"자동 조정되었습니다. 헤더의 '시드보다 더 담기 허용' 토글을 켜면 제한 없이 "
                f"입력할 수 있어요."
            ) if was_clamped else None

        def _weight_from_slider() -> None:
            _apply_clamped_weight(float(st.session_state[slider_key]))

        def _weight_from_number() -> None:
            _apply_clamped_weight(float(st.session_state[num_key]))

        # ---- 금액/수량 입력 카드가 보내온 값을 먼저 반영 ------------------------------
        # 반드시 아래 슬라이더/직접입력 위젯을 만들기 "전"이어야 합니다. Streamlit 은
        # 위젯이 만들어진 뒤에 그 위젯의 session_state 를 고치는 것을 막기 때문입니다
        # (on_change 콜백은 렌더 전에 실행돼서 괜찮지만, 이건 렌더 도중 실행됩니다).
        # compute() 가 아직 안 돌았으므로, 여기서 현재가를 미리 조회합니다(캐시라 저렴함).
        qty_price_native, qty_price_source, _, qty_price_warn = resolve_price(sel)
        qty_is_us_usd = sel.market == "US" and sel.currency == "USD"
        qty_fx = fx_service.current_usdkrw() if qty_is_us_usd else None
        qty_price_krw = None
        if qty_price_native is not None:
            if qty_is_us_usd:
                qty_price_krw = (qty_price_native * qty_fx.rate
                                 if (qty_fx and qty_fx.ok) else None)
            else:
                qty_price_krw = qty_price_native

        def _weight_from_qty(qty: float, _price_krw=qty_price_krw) -> None:
            cap = P.initial_capital_krw
            if _price_krw and _price_krw > 0 and cap > 0:
                # 목표금액(calculate_target_amount)은 내부적으로 원 단위 소수점 2자리로
                # 반올림합니다. 수량×가격이 정수 배수와 정확히 맞아떨어지는 경계에서는
                # 그 반올림이 "내림" 방향으로 떨어지면 floor(목표금액/가격) 계산에서 입력한
                # 수량보다 1주 적게 나올 수 있어, 0.5원의 아주 작은 여유값을 더해 항상
                # 목표금액이 (수량×가격) 이상이 되도록 보정합니다. 실제 종목 가격은 전부
                # 수백~수십만 원대라 0.5원은 다음 주(share) 경계를 절대 넘지 않습니다.
                _apply_clamped_weight((qty * _price_krw + 0.5) / cap * 100.0)

        def _weight_from_amount(amount_krw: float) -> None:
            cap = P.initial_capital_krw
            if cap > 0:
                _apply_clamped_weight(amount_krw / cap * 100.0)

        # 같은 입력을 매 렌더마다 다시 적용하지 않도록 nonce 로 "새 입력"일 때만 반영
        buy_key, nonce_key = f"buy_{sel.id}", f"buy_nonce_{sel.id}"
        pending = st.session_state.get(buy_key)
        if pending and pending.get("nonce") != st.session_state.get(nonce_key):
            # nonce 는 값이 멀쩡하든 아니든 먼저 소비합니다. 안 그러면 이상한 값이
            # 매 렌더마다 다시 들어와서 같은 판단을 계속 반복하게 됩니다.
            st.session_state[nonce_key] = pending.get("nonce")
            # ⚠ 이 값은 **브라우저에서 온 외부 입력**입니다. 받는 쪽에서 검사합니다.
            #   NaN 이 들어오면 clamp 가 min(100, nan) -> 100 을 돌려줘서
            #   비중이 조용히 100% 로 튑니다(다른 종목이 전부 눌립니다).
            #   재현이 어려워 "가끔 비중이 이상해진다" 는 제보로만 올 유형이라,
            #   아예 무시하고 지금 비중을 그대로 둡니다.
            _src = pending.get("source")
            _raw = pending.get("qty") if _src == "qty" else pending.get("amount")
            if numbers.is_finite_number(_raw) or _raw in (None, "", 0):
                _value = numbers.safe_float(_raw, default=0.0, minimum=0.0)
                if _src == "qty":
                    _weight_from_qty(_value)
                else:
                    _weight_from_amount(_value)

        wc1, wc2 = st.columns([3, 1])
        with wc1:
            st.slider(
                "살(BUY) 비율 (%)", min_value=0.0, max_value=100.0, step=0.5,
                key=slider_key, on_change=_weight_from_slider,
                help=("내 시드 중 이 종목에 배분하려는 비율입니다.\n\n"
                      "이 종목에 넣을 돈 = 내 시드 × 살(BUY) 비율\n\n"
                      "예: 시드 1억원의 20% → 이 종목에 넣을 돈 2천만원. "
                      "이 금액을 넘지 않는 선에서 정수 주식을 최대한 삽니다. "
                      "그래서 '실제로 들어간 비율'은 이 값과 조금 다를 수 있어요."),
            )
        with wc2:
            st.number_input(
                "직접입력(%)", min_value=0.0, max_value=100.0, step=0.5,
                key=num_key, on_change=_weight_from_number,
            )

        # 지금 비중 기준의 금액/수량을 내려보내면, 한쪽 칸을 고쳤을 때 다른 칸도 같이
        # 맞춰집니다 (금액을 치면 몇 주인지, 수량을 치면 얼마인지가 서로 반영됨).
        cur_amount = float(st.session_state[slider_key]) / 100.0 * P.initial_capital_krw
        if qty_price_krw:
            cur_qty = (calculation_service.calculate_fractional_shares(cur_amount, qty_price_krw)
                       if P.fractional_shares
                       else calculation_service.calculate_integer_shares(cur_amount, qty_price_krw))
        else:
            cur_qty = 0.0

        buy_input(
            amount=cur_amount, qty=cur_qty,
            price_krw=qty_price_krw, price_native=qty_price_native,
            currency=sel.currency,
            fx_rate=(qty_fx.rate if (qty_is_us_usd and qty_fx and qty_fx.ok) else None),
            fractional=P.fractional_shares, price_warning=qty_price_warn or "",
            echo=int(st.session_state.get(nonce_key) or 0),
            key=buy_key,
        )

        _clamp_msg = st.session_state.pop("weight_clamp_warning", None)
        if _clamp_msg:
            st.warning(_clamp_msg)

        sel.target_weight = float(st.session_state[slider_key]) / 100.0

        sel.distribution_enabled = st.checkbox("분배금 계산에 넣기", value=sel.distribution_enabled,
                                               key=f"de_{sel.id}")
        method_label = st.radio(
            "분배금 계산 방법", ["자동 (최근 12개월)", "직접 입력"],
            index=0 if sel.distribution_method == DIST_METHOD_AUTO else 1,
            key=f"dm_{sel.id}", horizontal=True,
        )
        _step = 1.0 if sel.currency == "KRW" else 0.01   # 원화는 소수점 단위가 없음
        if method_label == "직접 입력":
            sel.distribution_method = DIST_METHOD_MANUAL
            sel.manual_ttm_per_share = st.number_input(
                f"최근 12개월 주당 분배금 ({sel.currency})", min_value=0.0, step=_step,
                value=float(sel.manual_ttm_per_share or 0.0), key=f"mt_{sel.id}",
            )
        else:
            sel.distribution_method = DIST_METHOD_AUTO

        with st.expander("수동 가격 입력 (자동 조회 실패 시)"):
            mp = st.number_input(f"1주 가격 ({sel.currency})", min_value=0.0, step=_step,
                                 value=float(sel.manual_price or 0.0), key=f"mp_{sel.id}")
            sel.manual_price = mp if mp > 0 else None

# ---- 계산 (네트워크 -> 캐시). 위의 편집 위젯이 모두 반영된 뒤에 실행 ----------
with st.spinner("가격·환율·분배금 계산 중..."):
    comp = portfolio_service.compute(P)

# ---- 위쪽 간략 요약 바 채우기 (상세 요약은 맨 아래에 그대로 유지) --------------
with summary_bar_slot:
    summary_strip([
        ("내 시드", won(comp.initial_capital_krw), False),
        ("총 원금", won(comp.total_actual_investment_krw), False),
        ("잔여현금", won(comp.cash_balance_krw), comp.cash_balance_krw < 0),
        ("월 분배금", won(comp.monthly_distribution_krw), False),
        ("연 분배금", won(comp.annual_distribution_krw), False),
        # 분모를 '실제 투자금'으로 씁니다. 시드를 다 담지 않았을 때 시드 기준으로 보여주면
        # "분배율 15% 짜리를 담았는데 왜 0.7% 라고 나오지?" 하는 오해가 생깁니다.
        # "투자금 대비" 만 적으면 무엇 대비 무엇인지 몰라서 처음 보는 사람은
        # 감을 못 잡습니다. 무슨 비율인지까지 적습니다 (사용자 요청).
        ("투자금 대비 분배율", pct(comp.income_yield_on_invested_pct), False),
    ])
    # ---- 내 목표 (사용자 요청) --------------------------------------------
    # 숫자로 된 목표가 생기면 사람은 **그 숫자를 보러 돌아옵니다.**
    # 목표는 전술이 아니라 사람의 것이라, 슬롯을 바꿔도 그대로 남습니다.
    # 그래야 "공격안으로 바꾸니 41% -> 78% 가 되네" 가 보입니다.
    _gc1, _gc2 = st.columns([1, 2.1])
    with _gc1:
        _goal = money_input(
            "내 목표 (월 분배금, ₩)", key="money_goal",
            default_value=float(st.session_state.get("goal_monthly_krw") or 0.0),
            min_value=0,
            help="'월 100만원 받기' 처럼 받고 싶은 월 분배금을 적으세요. "
                 "0 이면 목표를 안 씁니다. 전술을 바꿔도 목표는 그대로 남습니다.",
        )
        st.session_state["goal_monthly_krw"] = _goal
    with _gc2:
        st.markdown("<div style='height:1.7rem'></div>", unsafe_allow_html=True)
        if _goal > 0:
            _ratio = calculation_service.progress_to_goal(
                comp.monthly_distribution_krw, _goal)
            st.progress(min(1.0, _ratio),
                        text=f"지금 월 {won_short(comp.monthly_distribution_krw)} · "
                             f"목표의 {pct(_ratio * 100, 1)}")
            _need = calculation_service.capital_needed_for_goal(
                comp.initial_capital_krw, comp.monthly_distribution_krw, _goal)
            if _ratio >= 1.0:
                note(f"목표를 넘었습니다. 지금 구성으로 월 "
                     f"<b>{won_short(comp.monthly_distribution_krw)}</b> 입니다.")
            elif _need is not None:
                note(f"지금 이 구성 그대로 <b>시드만</b> "
                     f"<b>{won_short(_need)}</b> 으로 늘리면 월 "
                     f"<b>{won_short(_goal)}</b> 이 됩니다. "
                     f"<span style='opacity:.75'>(지금 시드 {won_short(comp.initial_capital_krw)} · "
                     f"분배율이 달라지면 결과도 달라집니다)</span>")
            else:
                st.caption("아직 분배금이 0 이라 얼마가 더 필요한지 계산할 수 없습니다. "
                           "종목을 담아보세요.")

    # "월 얼마" 라는 숫자 하나 옆에, 그게 **언제 어느 종목에서** 들어오는지 여는 문.
    # 포트폴리오를 짜는 건 한 번이지만 이건 매달 궁금해집니다.
    if comp.rows and st.button("📅 분배금 달력 — 언제 얼마 들어오나", key="cal_open_btn",
                               help="새 데이터를 받아오지 않습니다. 이미 계산에 쓴 "
                                    "지급 이력을 날짜별로 펼쳐서 보여줍니다."):
        st.session_state["cal_open"] = True
        st.session_state["cal_ym"] = (config.today_local().year, config.today_local().month)
        st.rerun()

# ---- 📅 분배금 달력 (떠 있는 창) ------------------------------------------
def _close_calendar() -> None:
    st.session_state["cal_open"] = False


# ⚠ on_dismiss 를 반드시 달아야 합니다. 안 달면 창의 X 로 닫아도 cal_open 이 True 로
#   남아서, **다음에 아무 버튼이나 누르는 순간 달력이 혼자 다시 열립니다.**
#   (브라우저에서만 재현되는 동작이라 AppTest 로는 못 잡습니다 -- 실제로 그렇게 잡았습니다)
@st.dialog("📅 분배금 달력", width="large", on_dismiss=_close_calendar)
def _distribution_calendar() -> None:
    """언제 얼마가 들어오는지 달별로. **새 데이터를 받아오지 않습니다.**

    달을 넘기는 버튼은 화면을 그리기 **전에** 먼저 읽습니다. 나중에 읽으면 이번
    렌더는 옛날 달을 그린 뒤라서 한 박자 늦게 바뀝니다.
    """
    _y, _m = st.session_state.get(
        "cal_ym", (config.today_local().year, config.today_local().month))
    n1, n2, n3 = st.columns([1, 2.2, 1])
    _prev = n1.button("◀ 이전 달", width="stretch", key="cal_prev",
                      disabled=not calendar_service.can_go(comp, _y, _m, -1))
    _next = n3.button("다음 달 ▶", width="stretch", key="cal_next",
                      disabled=not calendar_service.can_go(comp, _y, _m, +1))
    if _prev:
        _y, _m = calendar_service.shift_month(_y, _m, -1)
    elif _next:
        _y, _m = calendar_service.shift_month(_y, _m, +1)
    st.session_state["cal_ym"] = (_y, _m)

    plan = calendar_service.month_plan(comp, _y, _m)
    n2.markdown(f"<div style='text-align:center;font-size:17px;font-weight:700;"
                f"padding-top:5px'>{html.escape(plan.title)}</div>",
                unsafe_allow_html=True)

    if not plan.in_range:
        st.info(f"지급 이력이 {calendar_service.MONTH_RANGE}개월치뿐이라 이 달은 "
                f"보여드릴 근거가 없습니다.")
        return

    st.markdown(f"#### {won(plan.total_krw)}")
    if plan.basis == calendar_service.BASIS_FORECAST:
        dialog_note("지난 12개월 지급 패턴으로 만든 <b>예상</b>입니다. "
                    "실제 지급일·금액은 달라질 수 있어요.")
    else:
        # 지나간 달이라도 수량은 '지금' 담은 수량입니다. 그때 이 종목을 갖고 있었는지는
        # 우리가 모르므로 "받으셨습니다" 라고 말하면 안 됩니다.
        dialog_note("그 달에 <b>실제로 지급된</b> 금액입니다. 다만 수량은 지금 담은 것 "
                    "기준이라, <b>지금 이 구성이었다면</b> 이만큼이라는 뜻입니다.")

    if plan.fx_missing:
        st.warning("환율을 가져오지 못해 미국 종목은 빼고 계산했습니다.")

    if plan.entries:
        st.dataframe(
            pd.DataFrame([{
                "날짜": f"{e.day:%m/%d}",
                "종목": e.label,
                "금액": won(e.amount_krw),
            } for e in plan.entries]),
            width="stretch", hide_index=True,
        )
    else:
        st.info("이 달에는 들어오는 분배금이 없습니다.")

    if plan.silent:
        dialog_note("이 달 지급 없음 — "
                    + " · ".join(html.escape(n) for n in plan.silent))

    _cc1, _cc2 = st.columns([1.6, 1])
    with _cc2:
        table_capture(
            title=f"📅 {plan.title}",
            subtitle=f"{_live_name()} · 합계 {won(plan.total_krw)}",
            sections=[{"columns": ["날짜", "종목", "금액"],
                       "rows": calendar_service.capture_rows(plan)}],
            notes=calendar_service.capture_notes(plan),
            footer=f"⚽ {config.app_name()} · {config.APP_PUBLIC_URL}",
            filename=config.table_image_filename(
                f"분배금달력_{plan.year}{plan.month:02d}", _live_name()),
            key="cal_capture",
        )
    with _cc1:
        if st.button("닫기", width="stretch", key="cal_close"):
            _close_calendar()
            st.rerun()


if st.session_state.get("cal_open") and comp.rows:
    _distribution_calendar()


# ---- ⇄ 두 전술 나란히 비교 (떠 있는 창) ------------------------------------
def _close_compare() -> None:
    """창을 닫습니다.

    비교를 **버튼**으로 열기 때문에 여기서는 상태 하나만 끄면 됩니다.
    드롭다운이었을 때는 고른 값을 되돌려놓아야 했고(안 그러면 닫자마자 다시 열림),
    그 되돌리기가 위젯 생성 뒤에 일어나 예외가 나서 쪽지를 남기는 장치까지
    필요했습니다. 버튼으로 바꾸면서 그게 전부 사라졌습니다.
    """
    st.session_state["cmp_open"] = False


@st.dialog("⇄ 두 전술 비교", width="large", on_dismiss=_close_compare)
def _compare_dialog(target_index: int) -> None:
    slots = st.session_state["slots"]
    if not (0 <= target_index < len(slots)):
        _close_compare()
        return
    other = slots[target_index]

    # ⚠ 여기서만 계산합니다. 첫 화면에서 자동으로 돌면 평소 속도가 느려집니다.
    with st.spinner(f"'{other.name}' 을 계산하는 중..."):
        b_comp = portfolio_service.compute(other.to_portfolio())

    # 표 머리에 **전술 이름을 그대로** 씁니다. "지금 / 저쪽" 은 한 번 더 머릿속에서
    # 옮겨야 해서, 전술이 늘어날수록 어느 쪽이 뭔지 헷갈립니다.
    _a_name = _live_name()
    _b_name = other.name

    def _cell(text: str, is_winner: bool, bar_pct: float | None) -> str:
        # 값 아래 얇은 막대. "124만" 과 "41.7만" 이 몇 배인지 한눈에 보이게 합니다.
        bar = ""
        if bar_pct is not None:
            bar = f"<span class='b'><i style='width:{bar_pct:.2f}%'></i></span>"
        return (f"<td class='v{' win' if is_winner else ''}'>"
                f"<span class='n'>{html.escape(text)}</span>{bar}</td>")

    _rows_html = []
    _all_rows = compare_service.rows(comp, b_comp)
    for _idx, row in enumerate(_all_rows):
        win = row.winner
        bars = row.bars
        # 비교해도 되는 줄(분배금·분배율)과 그냥 사실인 줄 사이에 선을 하나 긋습니다.
        # 어디까지가 "많을수록 원하던 것" 인지가 선 하나로 보입니다.
        sep = (_idx + 1 < len(_all_rows)
               and row.higher_is_what_you_asked_for
               and not _all_rows[_idx + 1].higher_is_what_you_asked_for)
        _rows_html.append(
            f"<tr{' class=\"sep\"' if sep else ''}>"
            f"<td class='k'>{html.escape(row.label)}</td>"
            + _cell(row.a_text, win == "a", bars[0] if bars else None)
            + _cell(row.b_text, win == "b", bars[1] if bars else None)
            + "</tr>"
        )
    st.markdown(
        "<table class='cmp'><thead><tr><th></th>"
        f"<th class='who mine'>{html.escape(_a_name)}"
        f"<span class='now'>지금 보는 것</span></th>"
        f"<th class='who'>{html.escape(_b_name)}</th></tr></thead><tbody>"
        + "".join(_rows_html) + "</tbody></table>",
        unsafe_allow_html=True,
    )
    dialog_note("초록은 <b>월 분배금·분배율</b> 처럼 '많을수록 원하던 것' 인 줄에만 "
                "칠합니다. 커버드콜 비중이나 종목 수는 많다고 좋은 게 아니라서 "
                "칠하지 않습니다.")

    _goal_line = compare_service.goal_progress_line(
        comp, b_comp, float(st.session_state.get("goal_monthly_krw") or 0.0))
    if _goal_line:
        note(f"<b>{html.escape(_b_name)}</b> 으로 바꾸면 — {html.escape(_goal_line)}")

    _both = compare_service.overlap(comp, b_comp)
    if _both:
        dialog_note(f"<b>둘 다 담은 종목 {len(_both)}개</b> — "
                    + " · ".join(html.escape(n) for n in _both))
    else:
        dialog_note("겹치는 종목이 없습니다.")

    # 전술판처럼 이 표도 그림으로 복사·저장할 수 있게 합니다.
    _cap1, _cap2 = st.columns([1.6, 1])
    with _cap2:
        table_capture(
            title="두 전술 비교",
            subtitle=f"{_a_name}  vs  {_b_name} · {config.today_local():%Y-%m-%d} 기준",
            sections=[{"columns": ["", _a_name, _b_name],
                       "rows": compare_service.capture_rows(comp, b_comp)}],
            notes=([_goal_line] if _goal_line else [])
                  + ["초록은 '많을수록 원하던 것' 인 줄에만 칠했습니다.",
                     ("둘 다 담은 종목 — " + " · ".join(_both)) if _both
                     else "겹치는 종목이 없습니다."],
            footer=f"⚽ {config.app_name()} · {config.APP_PUBLIC_URL}",
            filename=config.table_image_filename("비교", _a_name),
            key="cmp_capture",
        )
    with _cap1:
        if st.button("닫기", width="stretch", key="cmp_close"):
            _close_compare()
            st.rerun()


if st.session_state.get("cmp_open"):
    _compare_dialog(int(st.session_state.get("cmp_target", 0)))

# ---- 중: 전술판 (세로, FM 풍 포지션 슬롯) -----------------------------
with col_mid:
    warn_ids = {r.security.id for r in comp.rows if r.warnings}
    # 주장 완장 = 비중이 가장 큰 종목. 축구 화면에서 완장의 뜻은 설명이 필요 없고,
    # "이 포트의 중심이 뭔지" 가 한눈에 보입니다.
    _captain_id = formation_service.captain_id(P)
    # 카드 = 유니폼. 색(운용사 브랜드/성조기)과 줄인 이름은 pitch_kit 이 정합니다.
    players_payload = [{
        "id": s.id, "ticker": s.ticker, "display_name": s.display_name, "market": s.market,
        "label": pitch_kit.card_label(s.market, s.ticker, s.display_name, s.card_label),
        "kit": pitch_kit.kit_of(s.market, s.display_name),
        "weight_pct": s.target_weight * 100.0,
        "slot": s.slot,
        "has_warning": s.id in warn_ids,
        "captain": s.id == _captain_id,
    } for s in P.securities]

    # ---- 📸 캡처 이미지에만 구워지는 부분 (화면에는 안 나옴) --------------------
    # 전술판만 캡처하면 "그래서 얼마 버는데?" 가 안 보여서, 커뮤니티에 올려도
    # 감이 안 온다는 피드백에서 나왔습니다. 이미지 한 장에 배치·비율·원금·분배금·
    # 정식 종목명·기준일·주소가 전부 들어가게 합니다 (사용자 요청).
    capture_summary = {
        "cells": [
            {"k": "총 원금", "v": won_short(comp.total_actual_investment_krw)},
            # 월 분배금은 "이번 달 실제 입금액"이 아니라 연 합계 / 12 입니다.
            # 분기배당 종목을 섞으면 달마다 들쭉날쭉하므로 '월평균'이라고 적습니다.
            {"k": "월평균 분배금", "v": won_short(comp.monthly_distribution_krw)},
            {"k": "연 분배금", "v": won_short(comp.annual_distribution_krw)},
            {"k": "원금 대비", "v": pct(comp.income_yield_on_invested_pct)},
        ],
        # 이미지는 맥락 없이 혼자 돌아다니므로, 세전이라는 점과 기준일을 꼭 박습니다.
        # (미국 15% 원천징수, 국내 15.4% 배당소득세를 실수령으로 오해하면 손해)
        "note": f"※ 세전 · 최근 12개월 분배금 기준 · {config.today_local():%Y-%m-%d}",
        # "등번호"는 축구를 아는 사람에게만 통하는 말이라 풀어 썼습니다(사용자 요청).
        "key_note": "유니폼 숫자 = 그 종목을 몇 % 담았는지 · 흰 유니폼 = 미국 종목",
    }
    # 명단: 카드에는 이름을 줄여 쓰므로, 여기서 정식 명칭을 보증합니다.
    capture_legend = []
    for r in sorted(comp.rows, key=lambda r: -r.security.target_weight):
        s = r.security
        kit = pitch_kit.kit_of(s.market, s.display_name)
        name = (f"{s.display_name} ({s.ticker})" if s.market == MARKET_KR
                else (s.ticker or s.display_name))
        capture_legend.append({
            "name": name,
            "amount": (f"{pct(s.target_weight * 100)} · {won_short(r.actual_investment_krw)}"
                       f" · 월 {won_short(r.monthly_distribution_krw)}"),
            "color": kit["dark"],
            "us": kit["style"] == "us",
        })

    # 전술판 위 "📋 텍스트" 버튼이 복사할 글자. 아래 접힌 칸에 보여주는 것과 같은 값입니다.
    _comment_text = comment_text(comp) if P.securities else ""

    result = football_pitch(players=players_payload, slots=pitch_grid.slot_meta(),
                            selected_id=st.session_state.selected_id, key="pitch", height=760,
                            aspect_ratio=config.PITCH_ASPECT_RATIO,
                            summary=capture_summary, legend=capture_legend,
                            footer=f"⚽ {config.app_name()} · {config.APP_PUBLIC_URL}",
                            capture_filename=config.capture_image_filename(P.name),
                            comment_text=_comment_text)
    if result:
        for sec_id, slot_id in (result.get("assignments") or {}).items():
            sec = P.get(sec_id)
            if sec and pitch_grid.is_slot(slot_id) and sec.slot != slot_id:
                sec.place_in_slot(slot_id)
        # 전술판 컴포넌트는 마지막으로 클릭했던 종목을 계속 들고 있습니다. 그 종목을
        # 지운 뒤에도 그 값이 남아 있어서, 확인 없이 쓰면 "이미 지운 종목"이 다시
        # 선택된 것처럼 되살아납니다. 지금 실제로 담겨 있는 종목일 때만 받아들입니다.
        sid = result.get("selected_id")
        if sid and sid != st.session_state.selected_id and P.get(sid) is not None:
            st.session_state.selected_id = sid
            _dismiss_preset_confirm()
            st.rerun()

    if comp.weight_is_over:
        st.error(comp.weight_message)
    elif comp.cash_weight > 0:
        st.info(f"살(BUY) 비율 합계 {comp.weight_total*100:.2f}% · 나머지 "
                f"{comp.cash_weight*100:.2f}% 는 현금으로 남습니다.")

    # ---- 내가 뭘 담았나 (구성 막대 + 성향) --------------------------------
    # 표를 읽는 것과 막대 세 줄을 보는 것은 전혀 다릅니다.
    composition_bars(comp)

    # ---- 같은 지수를 여러 번 담았나 ---------------------------------------
    # 나스닥100 커버드콜을 셋 담아놓고 분산했다고 생각하는 경우가 많습니다.
    # 평가가 아니라 "자기가 뭘 담았는지" 를 보이게 하는 것입니다.
    _ov = overlap_service.check(P)
    if _ov.has_overlap:
        _lines = []
        for _g in _ov.groups:
            _who = " · ".join(f"{html.escape(n)} {w:.0f}%" for n, w in _g.members)
            _lines.append(
                f"<div class='ov-row'><span class='ov-tag'>{html.escape(_g.index_name)}</span>"
                f"<span class='ov-pct'>{_g.total_pct:.0f}%</span></div>"
                f"<div class='ov-who'>{_who}</div>")
        st.markdown(
            "<div class='ov-box'><div class='ov-head'>⚠ 같은 지수를 여러 번 담았습니다</div>"
            + "".join(_lines) + "</div>",
            unsafe_allow_html=True,
        )
    if _ov.unknown:
        # ⚠ 이 줄이 이 기능의 양심입니다. 표에 없는 종목을 조용히 빼고 "겹치는 것
        #   없음" 이라고 하면 그게 거짓말입니다. **"확인 못 함" 과 "안 겹침" 은
        #   다른 말**입니다.
        st.caption(f"**확인 못 한 종목 {len(_ov.unknown)}개** — "
                   + " · ".join(_ov.unknown)
                   + " · 기초지수 정보가 없어서 겹치는지 **모릅니다**. "
                     "(겹치지 않는다는 뜻이 아닙니다)")

    # ---- 포메이션 · 자동 정리 · 이름 추천 ---------------------------------
    if P.securities:
        _shape = formation_service.formation(P)
        _fc1, _fc2 = st.columns([1.25, 1])
        with _fc1:
            if _shape:
                st.caption(f"지금 배치 **{_shape}** "
                           f"<span style='opacity:.7'>(수비-미드-공격)</span>",
                           unsafe_allow_html=True)
        with _fc2:
            # ⚠ 절대 자동으로 옮기지 않습니다. 사용자가 손으로 맞춰둔 배치를 앱이
            #   말없이 흐트러뜨리면 화가 납니다. 눌렀을 때만 움직입니다.
            if st.button("⚽ 포지션 자동 정리", key="tidy_btn", width="stretch",
                         help="커버드콜·리츠는 공격, 배당주는 중앙, 채권은 수비로 "
                              "옮깁니다. 비중이 큰 종목이 가운데로 갑니다."):
                _moved = formation_service.tidy(P)
                st.session_state["tidy_note"] = (
                    f"{_moved}개 종목을 자리에 맞게 옮겼습니다. 배치 "
                    f"{formation_service.formation(P)}" if _moved
                    else "이미 자리에 맞게 놓여 있습니다.")
                st.rerun()
        _tidy_note = st.session_state.pop("tidy_note", None)
        if _tidy_note:
            st.caption(_tidy_note)

        # 슬롯이 생기면서 이름 지을 일이 자주 생깁니다. "새 전술 (2)" 가 쌓이면
        # 슬롯이 무용지물이 되므로, 담은 내용으로 기본 이름을 만들어 줍니다.
        _suggestion = formation_service.suggest_name(P, comp)
        if _suggestion and _suggestion != P.name:
            if st.button(f"✏️ 전술명을 '{_suggestion}' 로", key="name_suggest",
                         width="stretch"):
                st.session_state["pending_tactic_name"] = _suggestion
                st.rerun()

    # ---- 📋 텍스트 (사용자 요청) ----------------------------------------------
    # 네이버 댓글처럼 **이미지 첨부가 아예 안 되는 곳**이 많습니다. 📸 복사는
    # 글쓰기 창에 붙여넣을 수 있는 곳에서만 통해서, 글자로 옮길 길이 따로 필요합니다.
    # 복사는 전술판 위 "📋 텍스트" 버튼으로 한 번에 되고, 여기서는 **무엇이 복사되는지
    # 눈으로 확인**할 수 있게 접어 둡니다(펼쳐야 보이는 형태 유지 -- 사용자 요청).
    if _comment_text:
        with st.expander("포트폴리오 텍스트 복사"):
            st.code(_comment_text, language=None)
            st.caption("전술판 위 “📋 텍스트” 를 누르면 이 내용이 그대로 복사됩니다.")

# ---- 우 (Phase B): 선택 종목의 계산 결과 표시 --------------------------
with col_right:
    if sel is not None:
        row = next((r for r in comp.rows if r.security.id == sel.id), None)
        if row:
            price_native = (f"{native_amt(row.price_native, sel.currency)} {sel.currency}"
                            if row.price_native is not None else config.NO_DATA_TEXT)
            st.write(f"현재가격: {price_native}"
                     + (f"  ·  출처 {row.price_source}" if row.price_source else ""))
            m1, m2 = st.columns(2)
            m1.metric("살(BUY) 비율", pct(sel.target_weight * 100))
            m2.metric("실제로 들어간 비율", pct(row.actual_weight * 100))
            m3, m4 = st.columns(2)
            m3.metric("보유 주식 수", f"{row.shares:g}")
            m4.metric("이 종목에 들어간 돈", won(row.actual_investment_krw))
            is_est = row.distribution_is_estimated
            ttm_label = "주당 분배금 (연환산 추정)" if is_est else "최근 12개월 주당 분배금"
            ttm_txt = (config.NO_DATA_TEXT if row.ttm_per_share_native is None
                       else f"{native_amt(row.ttm_per_share_native, sel.currency, 4)} {sel.currency}")
            st.write(f"{ttm_label}: {ttm_txt}")
            m5, m6 = st.columns(2)
            m5.metric(
                "분배율 (연환산 추정)" if is_est else "분배율 (TTM)",
                pct(row.distribution_yield_pct) if row.distribution_yield_pct is not None
                else config.NO_DATA_TEXT,
                help="현재가 대비 최근 12개월(또는 연환산 추정) 분배금 비율 = 주당 분배금 ÷ 현재가 × 100. "
                     "은행 예금 금리처럼 '지금 가격 기준' 참고용 숫자이며, 매수/매도 추천이 아닙니다.",
            )
            m6.metric("한 달에 받을 분배금", won(row.monthly_distribution_krw))

            if row.distribution_months_since_listing is not None:
                # 상장 12개월 미만 -- 추정이든 아니든 눈에 띄게 경고로 표시 (사용자 요청)
                st.warning(row.distribution_note)
            elif row.distribution_note:
                st.caption(row.distribution_note)

            if row.distribution_window_start and row.distribution_window_end:
                exp_title = (f"분배율은 어떻게 계산됐나요? "
                            f"(실제 {row.distribution_n_payments}회 지급"
                            + (" · 연환산 추정)" if is_est else ")"))
                with st.expander(exp_title):
                    st.caption(
                        f"TTM 기준 기간: {row.distribution_window_start} ~ {row.distribution_window_end} "
                        f"(오늘 기준 최근 12개월) · 출처: {row.price_source or '–'}"
                        + (f" · 상장 후 약 {row.distribution_months_since_listing:.1f}개월"
                           if row.distribution_months_since_listing is not None else "")
                    )
                    if row.distribution_payments:
                        pay_df = pd.DataFrame([
                            {"지급일": d.isoformat(),
                             f"주당 분배금 ({sel.currency})": native_amt(amt, sel.currency, 4)}
                            for d, amt in row.distribution_payments
                        ])
                        st.dataframe(pay_df, hide_index=True, width="stretch")
                        if is_est:
                            st.caption(
                                f"위 {row.distribution_n_payments}건 실제 합계 = "
                                f"{native_amt(row.distribution_actual_total_native, sel.currency, 4)} "
                                f"{sel.currency} → 365일 기준으로 연환산 = "
                                f"{native_amt(row.ttm_per_share_native, sel.currency, 4)} {sel.currency} → "
                                f"현재가 {native_amt(row.price_native, sel.currency)} {sel.currency} "
                                f"로 나눈 값이 위 분배율(추정)입니다."
                            )
                        else:
                            st.caption(
                                f"위 {len(row.distribution_payments)}건 합계 = "
                                f"{native_amt(row.ttm_per_share_native, sel.currency, 4)} {sel.currency} → "
                                f"현재가 {native_amt(row.price_native, sel.currency)} {sel.currency} "
                                f"로 나눈 값이 위 분배율입니다."
                            )
                    elif sel.distribution_method == DIST_METHOD_MANUAL:
                        st.caption("사용자가 '직접 입력'한 값이라 개별 지급 내역은 없습니다.")
            for w in row.warnings:
                if w != row.distribution_note:   # 위에서 이미 경고로 보여준 것과 중복 방지
                    st.warning(w)

        st.divider()
        # 무엇이 지워지는지 버튼에 그대로 적습니다. 예전에는 "종목 제거" 라고만 되어 있어서,
        # 선택이 바뀌는 중에 누르면 엉뚱한 종목이 지워져도 알아채기 어려웠습니다.
        if st.button(f"🗑 {sel.display_name} 제거", type="secondary", width="stretch",
                     key=f"remove_{sel.id}"):
            P.remove(sel.id)
            st.session_state.selected_id = None
            _dismiss_preset_confirm()
            # 이 종목에 딸린 입력칸 상태도 같이 정리 (남아 있으면 다음 종목에 영향)
            for _k in (f"buy_{sel.id}", f"buy_nonce_{sel.id}",
                       f"wsel_{sel.id}", f"wsel_num_{sel.id}", f"lbl_{sel.id}"):
                st.session_state.pop(_k, None)
            st.rerun()

# =====================================================================
# 보유 종목 표 (목표비중 vs 실제비중 -- 인수인계서 30, 80)
# =====================================================================
if P.securities:
    st.markdown("#### 어떻게 살까? (종목별 상세)")
    df = pd.DataFrame([{
        "시장": "한국" if r.security.market == MARKET_KR else "미국",
        "종목": r.security.display_name if r.security.market == MARKET_KR else r.security.ticker,
        "현재가": (native_amt(r.price_native, r.security.currency)
                 if r.price_native is not None else "–"),
        "통화": r.security.currency,
        "분배율(TTM)": (
            (f"{r.distribution_yield_pct:.2f}%" + (" (추정)" if r.distribution_is_estimated else ""))
            if r.distribution_yield_pct is not None else "–"
        ),
        "살(BUY) 비율": f"{r.target_weight*100:.2f}%",
        "수량": f"{r.shares:g}",
        "종목 원금(₩)": f"{r.actual_investment_krw:,.0f}",
        "실제로 들어간 비율": f"{r.actual_weight*100:.2f}%",
        "한 달에 받을 분배금(₩)": f"{r.monthly_distribution_krw:,.0f}",
    } for r in comp.rows])

    # 맨 아래 합계 줄 (사용자 요청). 종목마다 가격/통화가 달라 의미가 없는 칸
    # (현재가·통화·수량·분배율)은 비워 둡니다 -- 섞어서 더하면 틀린 숫자가 됩니다.
    df.loc[len(df)] = {
        "시장": "", "종목": "합계", "현재가": "", "통화": "", "분배율(TTM)": "",
        "살(BUY) 비율": f"{sum(r.target_weight for r in comp.rows)*100:.2f}%",
        "수량": "",
        "종목 원금(₩)": f"{comp.total_actual_investment_krw:,.0f}",
        "실제로 들어간 비율": f"{sum(r.actual_weight for r in comp.rows)*100:.2f}%",
        "한 달에 받을 분배금(₩)": f"{comp.monthly_distribution_krw:,.0f}",
    }
    st.dataframe(df, width="stretch", hide_index=True)

# =====================================================================
# 포트폴리오 요약 (상세, 인수인계서 31, 82, 108)
# =====================================================================
# 여기까지 내려왔다면 포트폴리오를 다 짠 사람입니다. "그래서 매달 언제 얼마가
# 들어오나" 를 보러 갈 자리가 바로 여기라서, 요약 제목 바로 위에 크게 답니다.
st.markdown(
    f"<a class='paystub-cta' target='_blank' rel='noopener noreferrer' "
    f"href='{config.PAYSTUB_URL}'>{config.PAYSTUB_LABEL} ↗</a>",
    unsafe_allow_html=True,
)
st.markdown("### 포트폴리오 요약 (상세)")
s1, s2, s3 = st.columns(3)
s1.metric("내 시드", won(comp.initial_capital_krw))
s2.metric("총 원금", won(comp.total_actual_investment_krw))
s3.metric("잔여현금", won(comp.cash_balance_krw))
s4, s5, s6 = st.columns(3)
s4.metric("한 달에 받을 분배금", won(comp.monthly_distribution_krw))
s5.metric("연 예상 분배금", won(comp.annual_distribution_krw))
# 두 수익률을 나란히 보여줍니다. 시드를 다 담지 않으면 둘이 크게 벌어지는데,
# 하나만 보여주면 "분배율 15% 짜리를 담았는데 왜 0.7%?" 하는 오해가 생깁니다.
# "예상 수익" 은 가격이 올라서 버는 것까지 포함한다고 오해할 수 있어서 "분배율"로
# 통일했습니다. 위쪽 요약 바와도 같은 말을 씁니다 (사용자 요청).
s6.metric("투자금 대비 분배율", pct(comp.income_yield_on_invested_pct),
          help="실제로 종목에 들어간 돈 기준입니다. 담은 종목들의 평균 분배율에 해당하며, "
               "현금을 얼마나 남겨뒀는지와 무관합니다.")
s7, s8, _s9 = st.columns(3)
s7.metric("시드 대비 분배율", pct(comp.income_yield_pct),
          help="남겨둔 현금까지 포함한 내 시드 전체 기준입니다. 시드의 일부만 담으면 "
               "낮게 나오는 것이 정상이며, 현금을 놀리고 있다는 뜻입니다.")
if comp.cash_balance_krw > 0 and comp.initial_capital_krw > 0:
    _cash_pct = comp.cash_balance_krw / comp.initial_capital_krw * 100
    if _cash_pct >= 5:
        s8.metric("현금 비중", pct(_cash_pct),
                  help="시드 중 아직 종목에 넣지 않은 비율입니다.")
st.caption(config.DISTRIBUTION_DISCLAIMER)

cA, cB, cC = st.columns(3)
cA.caption(f"{config.DATA_AS_OF_LABEL}: {comp.data_as_of or config.NO_DATA_TEXT}")
cB.caption(f"{config.LAST_UPDATED_LABEL}: {comp.last_updated:%Y-%m-%d %H:%M} KST")
cC.caption(f"USD/KRW: {comp.usdkrw:,.2f} ({comp.usdkrw_as_of})" if comp.usdkrw
           else f"USD/KRW: {config.NO_DATA_TEXT}")

if comp.warnings:
    with st.expander(f"⚠ 데이터 경고 {len(comp.warnings)}건"):
        for w in comp.warnings:
            st.write("· " + w)

# =====================================================================
# 하단 도구: 저장 / 불러오기 / 백테스트 / 데이터 업데이트
# =====================================================================
st.divider()
b1, b2, b3 = st.columns(3)
with b1:
    st.download_button(
        "💾 전술 저장 (JSON)", data=tactic_service.to_json(P),
        file_name=tactic_service.export_filename(P), mime="application/json",
        width="stretch",
    )
with b2:
    up = st.file_uploader("📂 전술 불러오기 (JSON · ZIP)", type=["json", "zip"],
                          label_visibility="collapsed")
    if up is not None:
        sig = (up.name, up.size)
        if sig != st.session_state.last_upload_sig:
            st.session_state.last_upload_sig = sig
            # 전술 한 개(JSON)면 지금 슬롯만 바꾸고, 백업(ZIP)이면 슬롯 전체를 되살립니다.
            res = slot_service.read_upload(up.name, up.getvalue())
            if res.ok:
                _apply_slots(res.slots, replace_all=res.replace_all)
                # ⚠ 여기서 st.info() 를 부르면 바로 아래 st.rerun() 이 화면을 다시
                # 그리면서 그 메시지를 지워버립니다. 세션에 넣어뒀다가 다시 그린
                # 화면에서 보여줘야 사용자 눈에 들어옵니다.
                if res.message:
                    st.session_state["tactic_load_note"] = res.message
                st.rerun()
            else:
                st.error(res.message)
with b3:
    # 캐시 비우기는 관리자만 (사용자 요청).
    # 누구나 누를 수 있으면, 여러 명이 번갈아 누를 때마다 모든 시세를 다시 받아오게 되어
    # 데이터 제공처(야후/Alpaca)의 요청 한도에 걸립니다. 캐시는 모든 접속자가 공유하므로
    # 한 명의 클릭이 전체에 영향을 줍니다.
    if is_admin():
        if st.button("🔄 데이터 업데이트", width="stretch",
                     help="가격·환율·분배금 캐시를 비우고 최신 데이터를 다시 가져옵니다. "
                          "(관리자 전용)"):
            n = cache.invalidate()
            st.success(f"캐시 {n}건을 비웠습니다. 다시 계산합니다.")
            st.rerun()
    else:
        st.caption(f"시세는 자동으로 갱신됩니다 "
                   f"(최신가 {config.CACHE_TTL_LATEST_PRICE_SECONDS // 60}분 주기).")

# ---- 백테스트 (인수인계서 66~77) ----
with st.expander("📈 예전부터 해봤다면? (그냥 사서 계속 갖기)"):
    st.caption(config.BACKTEST_DISCLAIMER)

    # 아래 "이 날짜로 바꾸고 다시 실행" 버튼이 넣어둔 값을 여기서 꺼내 씁니다.
    # ⚠ 반드시 date_input 을 만들기 **전에** 해야 합니다. 위젯이 만들어진 뒤에
    # session_state 를 고치면 StreamlitWidgetAlreadyInstantiatedError 가 납니다.
    _pending_start = st.session_state.pop("bt_pending_start", None)
    if _pending_start is not None:
        st.session_state["bt_start"] = _pending_start

    f1, f2, f3 = st.columns([1, 1, 1])
    with f1:
        # key 로 값을 이미 넣어둔 상태에서 value= 까지 주면 Streamlit 이 경고를 남깁니다
        # ("created with a default value but also had its value set via the Session
        # State API"). 동작은 하지만 로그가 지저분해지고, 나중에 진짜 문제를 이 경고
        # 더미 속에서 못 찾게 됩니다. 처음 만들 때만 value 를 줍니다.
        _start_kw = ({} if "bt_start" in st.session_state
                     else {"value": date(2021, 1, 4)})
        bt_start = st.date_input("시작일", key="bt_start",
                                 min_value=date(1990, 1, 1), max_value=date.today(),
                                 **_start_kw)
    with f2:
        bt_cap = money_input("초기 투자금 (₩)", key="money_bt_capital",
                             default_value=P.initial_capital_krw, min_value=0)
    with f3:
        # 기본값을 켜둡니다. 여기 오는 사람은 대부분 **배당 포트폴리오**를 짜고 있고,
        # 분배금을 빼면 그 포트폴리오의 핵심 수익원이 통째로 빠진 숫자가 됩니다.
        # 더 나쁜 건 비교가 망가진다는 것입니다 -- 가격만 보면 고배당 ETF 는 성장주
        # ETF 에 항상 지는 것처럼 보입니다. 분배금으로 돌려준 몫이 주가에서 빠져
        # 있으니까요. 끄고 싶은 사람은 언제든 끌 수 있게 체크박스는 그대로 둡니다.
        bt_incl = st.checkbox(
            "분배금 포함 (현금 수령, 재투자 없음)", value=True,
            help="받은 분배금을 **현금으로 쌓아서** 더합니다(세전). 다시 사는 것으로 "
                 "치지 않으므로 '총수익률(재투자)'보다는 낮게 나옵니다. "
                 "끄면 주가 변동만 봅니다.")

    # 지금 화면이 어떤 조건인지를 한 덩어리로 묶어둡니다. 결과를 저장할 때 같이
    # 넣어두고, 나중에 다시 그릴 때 비교해서 "낡았는지"를 판단합니다.
    _bt_now = _backtest_signature(P, bt_start, bt_cap, bt_incl)

    # 날짜를 고쳐 넣은 직후에는 사용자가 "실행하기"를 한 번 더 누르지 않아도 되게 자동 실행.
    _autorun = st.session_state.pop("bt_autorun", False)
    if st.button("실행하기", type="primary") or _autorun:
        if not P.securities:
            st.warning("종목을 먼저 추가하세요.")
        else:
            with st.spinner("과거 데이터로 시뮬레이션 중..."):
                r = backtest_service.run_backtest(
                    P, bt_start, initial_capital_krw=float(bt_cap),
                    include_distributions=bt_incl)
            st.session_state["bt_result"] = r
            st.session_state["bt_signature"] = _bt_now
            # 결과에 "무엇을 돌린 것인지"를 항상 붙입니다. 이 줄은 화면을 캡처해
            # 공유할 때도 같이 나가서, 받는 사람이 조건을 알 수 있습니다.
            st.session_state["bt_context"] = (
                f"{len(P.securities)}종목 · 시드 {won(float(bt_cap))} · "
                f"{bt_start} 부터 · 분배금 {'포함' if bt_incl else '미포함'} · "
                f"{config.now_local():%Y-%m-%d %H:%M} 실행"
            )

    r = st.session_state.get("bt_result")
    if r is not None:
        # ---- 낡은 결과 안내 (지우지는 않습니다) ----------------------------
        # 종목을 지우거나 시드를 바꿔도 예전 결과가 그대로 남아 있어서, 바뀐 줄
        # 알고 옛날 숫자를 읽는 일이 잦았습니다. 그렇다고 결과를 지워버리면
        # "방금 본 게 어디 갔지" 가 되고 비교도 못 합니다. 남겨두되 말해줍니다.
        if st.session_state.get("bt_context"):
            st.caption(f"↩ 돌린 조건: {st.session_state['bt_context']}")
        if st.session_state.get("bt_signature") != _bt_now:
            st.warning("⚠ 이 결과는 **지금 화면과 다른 조건**으로 돌린 것입니다. "
                       "종목·시드·기간이 바뀌었어요. '실행하기'를 다시 눌러주세요.")
        if not r.ok:
            st.error(r.message)
            # 상장이 늦은 종목 때문에 막힌 경우: 날짜를 직접 옮겨 적지 않아도 되게
            # 한 번에 고쳐서 다시 돌려줍니다 (사용자 요청).
            if r.suggested_start:
                if st.button(f"📅 시작일을 {r.suggested_start} 로 바꾸고 다시 실행",
                             key="bt_fix_start", type="primary"):
                    st.session_state["bt_pending_start"] = r.suggested_start
                    st.session_state["bt_autorun"] = True
                    st.rerun()
        else:
            # ---- 한 문장 요약 (사용자 요청) --------------------------------
            # 표를 읽기 전에 "그래서 어땠는데?" 에 먼저 답합니다.
            # ⚠ 최대낙폭을 수익과 **같은 크기로** 씁니다. 수익만 크게 쓰면 앱이
            #   아니라 광고가 됩니다. 저 결과를 얻으려면 그 구간을 견뎌야 했습니다.
            _bt_years = ((r.data_as_of - r.actual_buy_date).days / 365.25
                         if r.actual_buy_date and r.data_as_of else 0.0)
            _line = (f"{r.actual_buy_date:%Y년 %m월}부터 {r.data_as_of:%Y년 %m월}까지"
                     f"({_bt_years:.1f}년) 이 구성이었다면, "
                     f"{won_short(r.initial_capital_krw)} 이 "
                     f"<b>{won_short(r.final_value_krw)}</b> 이 됐습니다.")
            # 분배금을 켜두는 것이 기본이라, **저 숫자에 무엇이 들어 있는지**를
            # 같이 말해야 합니다. 안 그러면 주가만 계산한 다른 곳 숫자와 나란히
            # 놓고 "여기가 더 좋네" 로 읽힙니다.
            if r.include_distributions and r.distributions_cash_krw > 0:
                # 조사는 "은" 으로 고정합니다. won_short() 는 항상 억/만/원 으로
                # 끝나고 셋 다 받침이 있어서, 규칙을 만들 필요가 없습니다.
                _line += (f" 이 중 <b>{won_short(r.distributions_cash_krw)}</b> 은 "
                          f"받은 분배금(세전)을 다시 사지 않고 현금으로 쌓은 것입니다.")
            if r.max_drawdown_pct < 0:
                _line += (f" 도중에 고점 대비 <b>{r.max_drawdown_pct:.1f}%</b> 까지 "
                          f"빠진 구간이 있었습니다"
                          + (f" ({r.max_drawdown_date:%Y년 %m월})" if r.max_drawdown_date
                             else "")
                          # 낙폭은 쌓인 분배금을 빼고 잽니다. 넣으면 하락이 실제보다
                          # 작아 보입니다(_max_drawdown 참고). 기준이 다르니 말해둡니다.
                          + (" — 쌓인 분배금은 빼고 잰 값입니다."
                             if r.include_distributions and r.distributions_cash_krw > 0
                             else "."))
            note(_line)

            st.markdown("**BACKTEST RESULT**")
            g1, g2, g3 = st.columns(3)
            g1.metric("초기 투자금", won(r.initial_capital_krw))
            # "평가금액" 한 칸에 주식·현금·분배금을 뭉쳐 놓으면, 얼마가 주가로 번 것이고
            # 얼마가 통장에 쌓인 현금인지 알 수가 없습니다. 합계는 합계라고 부르고,
            # 바로 아래에서 셋으로 쪼개서 보여줍니다 (사용자 요청).
            g2.metric("최종 자산 (합계)", won(r.final_value_krw),
                      help="주식 평가액 + 잔여현금"
                           + (" + 받은 분배금(세전, 재투자 없음)"
                              if r.include_distributions else "")
                           + ". 바로 아래에 쪼개서 적어뒀습니다.")
            # 시드의 일부만 담았으면 "전체 기준 수익률"은 현금에 희석돼 아주 작게 나옵니다.
            # (예: 1억 중 450만원만 담아 종목이 +21% 여도 전체로는 +1%)
            # 그래서 실제로 넣은 돈 기준 수익률을 같이 보여줍니다.
            _bt_on_invested = (r.profit_krw / r.total_invested_krw * 100.0
                               if r.total_invested_krw > 0 else 0.0)
            g3.metric("수익률 (투자금 기준)", f"{_bt_on_invested:+.2f}%",
                      delta=won(r.profit_krw),
                      help="실제로 종목에 들어간 돈 기준입니다. 아래 '전체 기준'은 "
                           "남겨둔 현금까지 포함한 값이라 더 낮게 나옵니다.")
            if abs(_bt_on_invested - r.return_pct) >= 0.01:
                _cash_ratio = (r.cash_balance_krw / r.initial_capital_krw * 100.0
                               if r.initial_capital_krw > 0 else 0.0)
                note(
                    f"초기 투자금 중 <b>{won(r.total_invested_krw)}</b> 만 종목에 들어갔습니다 "
                    f"(현금 <b>{_cash_ratio:.1f}%</b> 남음). "
                    f"남은 현금까지 포함하면 전체 기준 수익률은 "
                    f"<b>{r.return_pct:+.2f}%</b> 입니다."
                )
            # ---- 위 '최종 자산' 을 쪼갠 것 -------------------------------
            # 이 칸들을 더하면 **정확히** 위 합계가 됩니다. 성격이 다른 돈이라
            # 뭉쳐놓으면 안 됩니다 -- 주식은 오르내리지만 쌓인 현금은 안 움직입니다.
            st.caption("최종 자산을 쪼개면")
            if r.include_distributions:
                b1, b2, b3 = st.columns(3)
                b3.metric("받은 분배금 (세전)", won(r.distributions_cash_krw),
                          help="구간 중 받은 분배금을 다시 사지 않고 현금으로 쌓은 것입니다. "
                               "세금은 빼지 않았습니다.")
            else:
                b1, b2 = st.columns(2)
            b1.metric("주식 평가액", won(r.holdings_value_krw),
                      help="종료일 종가 x 보유수량 (미국 종목은 그날 환율로 원화 환산).")
            b2.metric("잔여현금", won(r.cash_balance_krw),
                      help="시드 중 종목에 못 들어가고 남은 돈입니다.")

            h1, h2, h3 = st.columns(3)
            h1.write(f"입력일: {r.input_start}")
            h2.write(f"실제 매수 기준일: {r.actual_buy_date}")
            h3.write(f"{config.DATA_AS_OF_LABEL}: {r.data_as_of}")
            st.write(f"총 원금: {won(r.total_invested_krw)}")
            btdf = pd.DataFrame([{
                # 위 "어떻게 살까?" 표와 같은 규칙. 한국 종목은 티커가 종목코드라
                # 그대로 쓰면 "458730" 처럼 떠서 뭘 백테스트한 건지 알 수가 없습니다.
                "종목": x.display_name if x.market == MARKET_KR else x.ticker,
                "살(BUY) 비율": f"{x.target_weight*100:.2f}%",
                "매수가": f"{native_amt(x.buy_price_native, x.currency)} {x.currency}",
                "살 때 환율": (f"{x.buy_fx:,.2f}" if x.buy_fx else "–"),
                "수량": f"{x.shares:g}",
                "살 때 원금(₩)": f"{x.invested_krw:,.0f}",   # 매수가 x 수량 (원화 환산)
                "구간내 분할": x.splits_in_period,
                "종료가": f"{native_amt(x.final_price_native, x.currency)} {x.currency}",
                "평가금액(₩)": f"{x.final_value_krw:,.0f}",
                "지금 환율": (f"{x.final_fx:,.2f}" if x.final_fx else "–"),
            } for x in r.rows])
            st.dataframe(btdf, width="stretch", hide_index=True)

            # 백테스트 결과도 전술판처럼 그림으로 복사·저장할 수 있게 합니다.
            # ⚠ 낙폭이 빠진 그림은 만들지 않습니다(backtest_service.capture_rows 참고).
            # 저장 버튼을 누른 사람은 "지금 보고 있는 이 화면" 이 저장될 거라고
            # 생각합니다. 그래서 요약뿐 아니라 **종목별 표까지** 같이 담습니다.
            _bt1, _bt2 = st.columns([2.2, 1])
            with _bt2:
                table_capture(
                    title="📈 백테스트 결과",
                    subtitle=(f"{P.name} · {len(r.rows)}종목 · 그냥 사서 계속 갖기 · "
                              f"{r.actual_buy_date} 매수 · "
                              f"{config.DATA_AS_OF_LABEL} {r.data_as_of}"),
                    sections=backtest_service.capture_sections(r),
                    notes=backtest_service.capture_notes(r),
                    footer=f"⚽ {config.app_name()} · {config.APP_PUBLIC_URL}",
                    filename=config.table_image_filename("백테스트", P.name),
                    key="bt_capture",
                )

            for w in r.warnings:
                st.caption("· " + w)

st.caption(
    "데이터 출처 — 미국: Alpaca Market Data / Yahoo Finance(yfinance) · "
    "한국: FinanceDataReader(KRX 기반) · 환율: yfinance/FinanceDataReader USD/KRW · "
    "분배금: 미국 Alpaca·yfinance / 한국 yfinance / (일부) 수동 입력. "
    "종목별 '현재가격' 옆에 실제로 사용된 출처가 표시됩니다. "
    "종목별 1주 가격·분배금은 해당 통화(USD/KRW)로 표시되고, 내 시드·총 원금·잔여현금·분배금 합계 등 "
    "포트폴리오 금액은 항상 원화(₩)로 환산해 표시합니다. "
    "본 도구는 포트폴리오 구성·계산 도구이며 투자 판단·추천을 제공하지 않습니다."
)

# =====================================================================
# 브라우저에 저장 (맨 마지막)
# =====================================================================
# ⚠ 반드시 화면을 다 그린 뒤여야 합니다. 이번에 사용자가 고친 값들이 P 에 반영되는
#    건 위쪽 위젯들이 다 돌고 난 다음이라, 맨 위에서 저장하면 한 박자 전 내용이
#    저장됩니다.
# 값이 바뀔 때만 브라우저가 답을 올려보내도록 컴포넌트 쪽에서 막아놨습니다.
# 안 그러면 슬라이더를 한 번 움직일 때마다 화면이 두 번 그려집니다.
_save_slots, _save_active = _slots_snapshot()
st.session_state["slots"] = _save_slots
local_store(mode="write", key="ls_write", data=slot_service.dumps(slot_service.StoreState(
    slots=_save_slots, active=_save_active,
    goal_monthly_krw=float(st.session_state.get("goal_monthly_krw") or 0.0),
)))
