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
import presets
from components.buy_input import buy_input
from components.football_pitch import football_pitch
from data.providers import cache
from data.providers import search_provider
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
    fx_service,
    portfolio_service,
    tactic_service,
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


def _reset_widgets_on_load() -> None:
    """새 전술을 불러왔을 때, 그 전술의 값으로 재초기화가 필요한 위젯들을 리셋."""
    for k in ("money_initial_capital", "money_bt_capital", "squad_full_toggle",
             "allow_overbudget_toggle"):
        st.session_state.pop(k, None)


_init_state()
P: Portfolio = st.session_state.portfolio
FULL_SQUAD = len(pitch_grid.all_slots())  # 전술판 전체 슬롯 수 (인수인계서 확장 요청 반영)


# =====================================================================
# 표시/입력 헬퍼
# =====================================================================
def won(x) -> str:
    if x is None:
        return config.NO_DATA_TEXT
    return f"₩{x:,.0f}"


def pct(x, digits: int = 2) -> str:
    if x is None:
        return config.NO_DATA_TEXT
    return f"{x:.{digits}f}%"


def native_amt(x, currency: str, usd_digits: int = 2) -> str:
    """종목의 "원래 통화" 기준 금액(가격/분배금 등) 표시. 원화는 소수점을 쓰지 않습니다.

    한국 원화는 실질적으로 1원 미만 단위가 없어 소수점이 의미가 없으므로 정수로,
    달러 등 다른 통화는 usd_digits 자리(기본 2자리)까지 보여줍니다.
    (환율 "비율" 자체는 여기 대상이 아닙니다 -- USD/KRW 환율 표시는 그대로 소수점 유지)
    """
    if x is None:
        return config.NO_DATA_TEXT
    if currency == "KRW":
        return f"{x:,.0f}"
    return f"{x:,.{usd_digits}f}"


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
    st.session_state.pop("bt_result", None)
    _reset_widgets_on_load()   # 시드 입력칸 등을 새 값으로 다시 채우기 위해


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
        return True
    except ValueError as e:
        st.warning(str(e))
        return False


# =====================================================================
# 헤더
# =====================================================================
st.markdown(
    f"<h2 class='app-title'>{config.app_name_with_icon()}"
    f"<span class='app-version'>{config.app_version_label()}</span></h2>",
    unsafe_allow_html=True,
)
hc1, hc2, hc3 = st.columns([2, 1, 1])
with hc1:
    P.name = st.text_input("전술명", value=P.name, placeholder="전술명")

    # ---- 예시로 시작하기 (사용자 요청) ----------------------------------------
    # 빈 화면에서 뭘 담아야 할지 막막하지 않도록, 버튼 한 번으로 채워지는 예시 3종.
    # 전술명 아래 남는 자리에 가로로 놓아 헤더 높이를 늘리지 않습니다.
    # 담긴 종목을 덮어쓰는 동작이라, 이미 담은 게 있으면 한 번 더 확인받습니다.
    st.caption(f"처음이라면 예시로 시작해보세요 (시드 {won(presets.PRESET_CAPITAL_KRW)} 기준) "
               f"· 예시일 뿐이며 투자 추천이 아닙니다.")
    for _col, _preset in zip(st.columns(len(presets.ALL_BUTTONS)), presets.ALL_BUTTONS):
        if _col.button(_preset.label, key=f"preset_{_preset.key}", width="stretch",
                       help=_preset.summary):
            if P.securities:
                st.session_state["preset_pending"] = _preset.key
            else:
                _apply_preset(_preset)
            st.rerun()

    _pending = presets.get(st.session_state.get("preset_pending") or "")
    if _pending:
        st.warning(
            f"지금 담은 종목 {len(P.securities)}개가 모두 지워집니다."
            if _pending is presets.RESET else
            f"'{_pending.label}' 예시를 불러오면 지금 담은 종목 "
            f"{len(P.securities)}개가 모두 지워집니다."
        )
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
    if "allow_overbudget_toggle" not in st.session_state:
        st.session_state["allow_overbudget_toggle"] = not P.strict_capital_limit
    allow_over = st.toggle(
        "시드보다 더 담기 허용", key="allow_overbudget_toggle",
        help="기본값 OFF: 종목 살(BUY) 비율 합계가 내 시드(100%)를 넘지 않도록 자동으로 "
             "잘라냅니다. 켜면 제한 없이 입력할 수 있고, 초과 시 경고만 표시합니다.",
    )
    P.strict_capital_limit = not allow_over

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
            st.rerun()
    st.caption("클릭하면 오른쪽 상세 패널에서 비중을 바로 설정할 수 있습니다.")

    st.divider()
    st.markdown("#### 종목 검색")
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
        # 전체 이름과 야후 파이낸스 바로가기를 함께 보여줍니다 (사용자 요청).
        st.markdown(
            f"**{html.escape(sel.display_name)}**  ·  `{html.escape(sel.ticker)}`  "
            f"<a class='ext-link' target='_blank' rel='noopener noreferrer' "
            f"href='{presets.toss_invest_url(sel.market, sel.ticker)}'>토스 ↗</a> "
            f"<a class='ext-link' target='_blank' rel='noopener noreferrer' "
            f"href='{presets.yahoo_finance_url(sel.market, sel.ticker)}'>야후 ↗</a>",
            unsafe_allow_html=True,
        )
        _full_name = sel.name or ""
        st.caption(
            (f"{_full_name} · " if _full_name and _full_name != sel.display_name else "")
            + f"{'한국' if sel.market == MARKET_KR else '미국'} · {sel.currency} · {sel.asset_type}"
        )

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
            st.session_state[nonce_key] = pending.get("nonce")
            if pending.get("source") == "qty":
                _weight_from_qty(float(pending.get("qty") or 0.0))
            else:
                _weight_from_amount(float(pending.get("amount") or 0.0))

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
        ("예상 수익", pct(comp.income_yield_pct), False),
    ])

# ---- 중: 전술판 (세로, FM 풍 포지션 슬롯) -----------------------------
with col_mid:
    warn_ids = {r.security.id for r in comp.rows if r.warnings}
    players_payload = [{
        "id": s.id, "ticker": s.ticker, "display_name": s.display_name, "market": s.market,
        "weight_pct": s.target_weight * 100.0,
        "slot": s.slot,
        "has_warning": s.id in warn_ids,
    } for s in P.securities]

    result = football_pitch(players=players_payload, slots=pitch_grid.slot_meta(),
                            selected_id=st.session_state.selected_id, key="pitch", height=760,
                            aspect_ratio=config.PITCH_ASPECT_RATIO)
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
            st.rerun()

    if comp.weight_is_over:
        st.error(comp.weight_message)
    elif comp.cash_weight > 0:
        st.info(f"살(BUY) 비율 합계 {comp.weight_total*100:.2f}% · 나머지 "
                f"{comp.cash_weight*100:.2f}% 는 현금으로 남습니다.")

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
            # 이 종목에 딸린 입력칸 상태도 같이 정리 (남아 있으면 다음 종목에 영향)
            for _k in (f"buy_{sel.id}", f"buy_nonce_{sel.id}",
                       f"wsel_{sel.id}", f"wsel_num_{sel.id}"):
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
st.markdown("### 포트폴리오 요약 (상세)")
s1, s2, s3 = st.columns(3)
s1.metric("내 시드", won(comp.initial_capital_krw))
s2.metric("총 원금", won(comp.total_actual_investment_krw))
s3.metric("잔여현금", won(comp.cash_balance_krw))
s4, s5, s6 = st.columns(3)
s4.metric("한 달에 받을 분배금", won(comp.monthly_distribution_krw))
s5.metric("연 예상 분배금", won(comp.annual_distribution_krw))
s6.metric("투자금 대비 예상 수익", pct(comp.income_yield_pct))
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
    up = st.file_uploader("📂 전술 불러오기 (JSON)", type=["json"], label_visibility="collapsed")
    if up is not None:
        sig = (up.name, up.size)
        if sig != st.session_state.last_upload_sig:
            st.session_state.last_upload_sig = sig
            res = tactic_service.from_json(up.getvalue())
            if res.ok:
                st.session_state.portfolio = res.portfolio
                st.session_state.selected_id = None
                _reset_widgets_on_load()
                if res.message:
                    st.info(res.message)
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
    f1, f2, f3 = st.columns([1, 1, 1])
    with f1:
        bt_start = st.date_input("시작일", value=date(2021, 1, 4),
                                 min_value=date(1990, 1, 1), max_value=date.today())
    with f2:
        bt_cap = money_input("초기 투자금 (₩)", key="money_bt_capital",
                             default_value=P.initial_capital_krw, min_value=0)
    with f3:
        bt_incl = st.checkbox("분배금 포함 (현금 수령, 재투자 없음)", value=False)

    if st.button("실행하기", type="primary"):
        if not P.securities:
            st.warning("종목을 먼저 추가하세요.")
        else:
            with st.spinner("과거 데이터로 시뮬레이션 중..."):
                r = backtest_service.run_backtest(
                    P, bt_start, initial_capital_krw=float(bt_cap),
                    include_distributions=bt_incl)
            st.session_state["bt_result"] = r

    r = st.session_state.get("bt_result")
    if r is not None:
        if not r.ok:
            st.error(r.message)
        else:
            st.markdown("**BACKTEST RESULT**")
            g1, g2, g3 = st.columns(3)
            g1.metric("초기 투자금", won(r.initial_capital_krw))
            g2.metric("최종 평가금액", won(r.final_value_krw))
            g3.metric("수익률", f"{r.return_pct:+.2f}%",
                      delta=won(r.profit_krw))
            h1, h2, h3 = st.columns(3)
            h1.write(f"입력일: {r.input_start}")
            h2.write(f"실제 매수 기준일: {r.actual_buy_date}")
            h3.write(f"{config.DATA_AS_OF_LABEL}: {r.data_as_of}")
            h4, h5, h6 = st.columns(3)
            h4.write(f"총 원금: {won(r.total_invested_krw)}")
            h5.write(f"잔여현금: {won(r.cash_balance_krw)}")
            if r.include_distributions:
                h6.write(f"분배금 누적(현금): {won(r.distributions_cash_krw)}")
            btdf = pd.DataFrame([{
                "종목": x.ticker,
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
