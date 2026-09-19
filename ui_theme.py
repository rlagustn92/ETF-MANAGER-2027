"""
ui_theme.py  --  화면 디자인(글꼴·글자색·크기·줄간격) 중앙 관리
================================================================

"글씨체/글자크기/줄간격을 바꾸고 싶다" -> 이 파일만 고치면 됩니다.

디자인 방향 (사용자 피드백 반영, 토스증권/Stripe 참고)
------------------------------------------------------
- 순검정 대신 짙은 네이비 "잉크" 하나를 기준으로, 진하게/연하게는 색을 바꾸지 않고
  그 잉크의 투명도만 다르게 써서 위계를 만듭니다 (INK_* 상수).
- 특이한 폰트를 새로 받지 않고 시스템 폰트 + 한글은 Noto Sans KR로 자연스럽게.
- 기본 글자 크기를 Streamlit 기본값보다 살짝 키우고, 줄간격을 넉넉하게(≈1.5~1.6배).
- 칸을 나눌 때 진한 테두리선 대신 아주 옅은 그림자로 살짝만 구분.

Streamlit 1.63.0 에서 실제로 확인한 data-testid 를 기준으로 타겟팅했습니다
(내부 해시 클래스명이 아니라 공개적으로 안정적인 data-testid 를 씁니다).
"""

from __future__ import annotations

import streamlit as st

# ---- 폰트 스택: 특이한 폰트를 새로 받지 않고, 있는 시스템 폰트 중 제일 깔끔한 걸 순서대로 ----
FONT_STACK = (
    '-apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans KR", '
    '"Malgun Gothic", "Apple SD Gothic Neo", Roboto, "Helvetica Neue", '
    'Arial, sans-serif'
)

# ---- 잉크(글자색) 시스템: 하나의 짙은 네이비를 기준으로 투명도만 바꿔서 위계를 만듦 ----
INK_RGB = "15, 42, 68"          # 짙은 네이비 (순검정 대신)
INK_PRIMARY = f"rgba({INK_RGB}, 0.92)"     # 제목/본문/강조 숫자
INK_LABEL = f"rgba({INK_RGB}, 0.84)"       # 입력칸 라벨 (눈에 잘 띄어야 하는 것)
INK_SECONDARY = f"rgba({INK_RGB}, 0.66)"   # 지표 라벨/보조 설명
INK_TERTIARY = f"rgba({INK_RGB}, 0.48)"    # 캡션/각주
INK_HAIRLINE = f"rgba({INK_RGB}, 0.08)"    # 아주 옅은 구분선/그림자


def inject() -> None:
    """앱 최상단(set_page_config 직후)에서 한 번 호출."""
    st.markdown(
        f"""
        <style>
        :root {{
          --ink-primary: {INK_PRIMARY};
          --ink-label: {INK_LABEL};
          --ink-secondary: {INK_SECONDARY};
          --ink-tertiary: {INK_TERTIARY};
          --ink-hairline: {INK_HAIRLINE};
        }}

        html, body, .stApp, [data-testid="stAppViewContainer"],
        [data-testid="stMarkdownContainer"] p,
        [data-testid="stMarkdownContainer"] li,
        [data-testid="stMarkdownContainer"] span,
        [data-testid="stWidgetLabel"] p,
        [data-testid="stCaptionContainer"],
        [data-testid="stCaptionContainer"] p,
        [data-testid="stMetricLabel"],
        [data-testid="stMetricValue"],
        [data-testid="stTextInputField"],
        [data-testid="stNumberInputField"],
        [data-testid="stSelectbox"],
        h1, h2, h3, h4, button, input, textarea, label {{
          font-family: {FONT_STACK} !important;
        }}

        /* 본문 텍스트: 살짝 크게 + 넉넉한 줄간격 + 짙은 네이비 잉크 */
        [data-testid="stMarkdownContainer"] p,
        [data-testid="stMarkdownContainer"] li {{
          font-size: 15.5px !important;
          line-height: 1.6 !important;
          color: var(--ink-primary) !important;
        }}

        /* 캡션/각주: 본문보다 살짝만 작고, 크기보다는 "옅은 색"으로 위계를 표현 */
        [data-testid="stCaptionContainer"],
        [data-testid="stCaptionContainer"] p {{
          font-size: 14.5px !important;
          line-height: 1.55 !important;
          color: var(--ink-tertiary) !important;
        }}

        /* 위젯 라벨(예: "내 시드 (₩)").
           연한 회색이라 잘 안 보인다는 피드백으로 잉크를 더 진하게 올렸습니다. */
        [data-testid="stWidgetLabel"] p {{
          font-size: 14.5px !important;
          font-weight: 600 !important;
          color: var(--ink-label) !important;
        }}

        /* 지표(st.metric): 값은 굵고 크게, 라벨은 그보다 작게 -- 숫자 중심 위계 */
        [data-testid="stMetricLabel"] {{
          font-size: 14px !important;
          font-weight: 600 !important;
          color: var(--ink-secondary) !important;
          letter-spacing: .01em;
        }}
        [data-testid="stMetricValue"] {{
          font-size: 30px !important;
          font-weight: 700 !important;
          color: var(--ink-primary) !important;
        }}

        h1, h2, h3 {{ color: var(--ink-primary) !important; }}
        h2 {{ font-size: 26px !important; }}
        h3, h4 {{ font-size: 18px !important; }}

        /* 전술판 위 한 줄 요약 박스. 라벨(작고 연하게) 위 / 숫자(크고 굵게) 아래로
           끊어 읽히게 해서, 길게 이어 쓸 때의 장황한 느낌을 없앱니다 (사용자 요청). */
        .stat-strip {{
          display: flex; flex-wrap: wrap;
          border: 1px solid var(--ink-hairline);
          border-radius: 12px;
          background: rgba(15, 42, 68, 0.022);
          padding: 11px 4px;
          margin: 2px 0 4px;
        }}
        .stat-strip .cell {{
          flex: 1 1 120px; min-width: 108px;
          padding: 1px 14px;
          border-left: 1px solid var(--ink-hairline);
        }}
        .stat-strip .cell:first-child {{ border-left: 0; }}
        .stat-strip .k {{
          font-size: 12.5px; font-weight: 600; color: var(--ink-tertiary);
          margin-bottom: 3px; white-space: nowrap;
        }}
        .stat-strip .v {{
          font-size: 17.5px; font-weight: 700; color: var(--ink-primary);
          font-variant-numeric: tabular-nums; line-height: 1.25;
        }}
        .stat-strip .v.neg {{ color: #cf3742; }}

        /* 종목명 옆 외부 링크(야후 파이낸스) */
        .ext-link {{
          display: inline-block;
          font-size: 12px; font-weight: 600; text-decoration: none;
          color: var(--ink-secondary) !important;
          border: 1px solid var(--ink-hairline);
          border-radius: 6px; padding: 1px 6px; margin-left: 2px;
          background: rgba(15, 42, 68, 0.04);
        }}
        .ext-link:hover {{ background: rgba(15, 42, 68, 0.10); }}

        /* 제목 옆 피드백 링크: 제목 글자 크기를 따라가지 않도록 크기를 고정하고
           버전 표시와 같은 높이에 놓습니다. */
        .ext-link.feedback {{
          margin-left: 10px;
          font-size: 12px;
          vertical-align: middle;
          white-space: nowrap;
        }}

        /* 자매 서비스(ETF INSIDE) 바로가기. 새로 연 서비스라 눈에는 띄어야 하지만,
           화면의 주인공은 전술판이라 옅은 파랑 한 겹까지만 씁니다. */
        .ext-link.inside {{
          margin-left: 8px;
          font-size: 12px;
          vertical-align: middle;
          white-space: nowrap;
          color: #1a5fb4 !important;
          border-color: rgba(26, 95, 180, 0.35);
          background: rgba(26, 95, 180, 0.07);
        }}
        .ext-link.inside:hover {{ background: rgba(26, 95, 180, 0.14); }}

        /* 좁은 칸(종목 검색 쪽)용. 제목 오른쪽에 그대로 붙이면 글자가 잘리므로
           바로 아래 한 줄짜리 버튼으로 눕힙니다. 글자는 똑같습니다. */
        .ext-link.inside.block {{
          display: block;
          margin: 2px 0 10px;
          padding: 7px 8px;
          text-align: center;
          white-space: normal;
          font-size: 12.5px;
        }}

        /* 그냥 지나치면 숫자를 오해하게 되는 설명. 일반 캡션(연한 회색)으로 쓰면
           눈에 안 들어와서, 옅은 황토 배경 + 왼쪽 굵은 선으로 시선을 잡아둡니다. */
        .note {{
          font-size: 15px;
          line-height: 1.6;
          font-weight: 500;
          color: var(--ink-primary);
          background: rgba(176, 116, 20, 0.07);
          border-left: 3px solid rgba(176, 116, 20, 0.6);
          border-radius: 8px;
          padding: 11px 14px;
          margin: 8px 0 4px;
        }}
        .note b {{ font-weight: 700; }}

        /* 오른쪽 위 방문자 수 (TODAY / TOTAL) */
        .visitors {{
          display: flex; justify-content: flex-end; gap: 14px;
          padding-top: 12px;
          font-size: 12.5px; color: var(--ink-tertiary);
          font-variant-numeric: tabular-nums; white-space: nowrap;
        }}
        .visitors b {{
          font-size: 11px; font-weight: 700; letter-spacing: .04em;
          color: var(--ink-tertiary); margin-right: 3px;
        }}

        /* 제목 옆 버전 표시 (config.APP_VERSION) */
        h2.app-title {{ margin: 0 0 .4rem; }}
        .app-version {{
          margin-left: 9px;
          font-size: 13px;
          font-weight: 600;
          color: var(--ink-tertiary);
          vertical-align: middle;
          letter-spacing: .02em;
        }}

        /* 같은 지수를 여러 번 담았을 때의 안내.
           평가가 아니라 사실 전달이라 빨강(오류)이 아니라 황토색을 씁니다. */
        .ov-box {{
          background: rgba(176, 116, 20, 0.07);
          border-left: 3px solid rgba(176, 116, 20, 0.6);
          border-radius: 8px; padding: 10px 13px; margin: 4px 0 6px;
        }}
        .ov-head {{
          font-size: 14px; font-weight: 700; color: rgba(138, 90, 11, 0.95);
          margin-bottom: 7px;
        }}
        .ov-row {{
          display: flex; justify-content: space-between; align-items: baseline;
          gap: 10px; font-size: 14px; font-weight: 600; color: var(--ink-primary);
        }}
        .ov-pct {{ font-variant-numeric: tabular-nums; }}
        .ov-who {{
          font-size: 12.5px; color: var(--ink-secondary);
          margin: 1px 0 8px; line-height: 1.5;
        }}
        .ov-who:last-child {{ margin-bottom: 0; }}

        /* 떠 있는 창(비교표·달력) 안의 설명.
           st.caption 은 아주 옅어서 흰 모달 위에서 거의 안 읽힙니다. 창 안의 설명은
           "그 표를 어떻게 읽어야 하는지" 를 말하는 것이라 한 단계 진하게 씁니다. */
        .dlg-note {{
          font-size: 14px; line-height: 1.65; color: var(--ink-secondary);
          margin: 2px 0 8px;
        }}
        .dlg-note b {{ color: var(--ink-primary); font-weight: 700; }}

        /* ---- 두 전술 비교 표 ------------------------------------------------
           이건 "읽는 표" 가 아니라 **두 덩어리를 견주는 화면** 입니다. 그래서
           줄무늬(가로)가 아니라 **열**이 나뉘어 보여야 합니다. 지금 보고 있는 쪽에만
           아주 옅은 바탕을 깔아서 두 열이 저절로 갈라지게 했습니다.
           색은 초록 하나만 씁니다. 여러 색을 쓰면 색이 곧 추천이 됩니다. */
        table.cmp {{
          width: 100%; border-collapse: separate; border-spacing: 0;
          margin: 2px 0 10px;
          border: 1px solid var(--ink-hairline); border-radius: 12px; overflow: hidden;
        }}
        table.cmp th {{
          text-align: left; padding: 13px 14px 11px;
          background: rgba(15, 42, 68, 0.028);
          border-bottom: 1px solid var(--ink-hairline);
        }}
        table.cmp td {{
          padding: 11px 14px; font-size: 16px; color: var(--ink-primary);
          border-bottom: 1px solid var(--ink-hairline);
          font-variant-numeric: tabular-nums; vertical-align: top;
        }}
        table.cmp tbody tr:last-child td {{ border-bottom: 0; }}
        /* 여기까지가 "많을수록 원하던 것", 아래는 그냥 사실 -- 선 하나로 구분 */
        table.cmp tbody tr.sep td {{ border-bottom: 1px solid var(--ink-hairline);
          box-shadow: 0 1px 0 var(--ink-hairline); }}

        table.cmp td.k {{
          color: var(--ink-secondary); font-size: 14px; font-weight: 600;
          width: 28%; padding-top: 13px;
        }}
        /* 지금 보고 있는 쪽 열에만 옅은 바탕 + 두 쪽 사이 세로 선.
           ⚠ td.v:first-of-type 으로 쓰면 안 됩니다 -- :first-of-type 은 클래스가 아니라
             **요소 종류** 기준이라 첫 번째 td(라벨 칸)를 가리키고, 클래스가 v 가 아니라서
             아무것도 안 걸립니다. 실제로 그렇게 써서 배경이 안 나왔습니다. */
        table.cmp th.mine, table.cmp td:nth-child(2) {{
          background: rgba(15, 42, 68, 0.04);
          border-right: 1px solid var(--ink-hairline);
        }}
        table.cmp td.v {{ font-weight: 600; }}
        table.cmp td.v .n {{ display: block; line-height: 1.25; }}
        table.cmp td.v.win .n {{ color: #1F6B47; font-weight: 700; }}

        /* 값 아래 얇은 막대 -- 몇 배 차이인지 즉시 보이게 */
        table.cmp td.v .b {{
          display: block; height: 3px; border-radius: 2px;
          background: rgba(15, 42, 68, 0.07); margin-top: 7px; max-width: 200px;
        }}
        table.cmp td.v .b i {{
          display: block; height: 100%; border-radius: 2px;
          background: rgba(15, 42, 68, 0.22);
        }}
        table.cmp td.v.win .b i {{ background: #1F6B47; }}

        /* 표 머리에 "지금/저쪽" 대신 전술 이름을 그대로 씁니다. 한 번 더 머릿속에서
           옮겨야 하는 말을 없애면 어느 쪽이 뭔지 헷갈릴 일이 없습니다. */
        table.cmp th.who {{
          font-family: inherit; font-size: 16.5px; font-weight: 700;
          color: var(--ink-primary); text-transform: none; letter-spacing: -.01em;
          line-height: 1.3;
        }}
        table.cmp th.who .now {{
          display: inline-block; margin-top: 5px;
          font-size: 11px; font-weight: 600; letter-spacing: .02em;
          color: var(--ink-secondary);
          background: rgba(15, 42, 68, 0.07);
          border-radius: 99px; padding: 1px 8px;
        }}
        @media (max-width: 560px) {{
          table.cmp td {{ font-size: 14.5px; padding: 9px 10px; }}
          table.cmp td.k {{ font-size: 13px; width: 30%; }}
          table.cmp th.who {{ font-size: 14.5px; }}
        }}

        /* 구성 막대 (어느 나라 / 어떤 종류 / 언제 들어오나).
           도넛 대신 가로 막대인 이유: 폰에서 도넛은 조각 안에 글자가 안 들어갑니다. */
        .comp-wrap {{ margin: 2px 0 6px; }}
        .comp-row {{ margin-bottom: 9px; }}
        .comp-title {{
          font-size: 12px; font-weight: 600; color: var(--ink-tertiary);
          margin-bottom: 4px;
        }}
        .comp-stack {{
          display: flex; height: 22px; border-radius: 6px; overflow: hidden;
          font-size: 11px; font-weight: 700;
        }}
        .comp-stack b {{
          display: flex; align-items: center; justify-content: center;
          min-width: 0; overflow: hidden; white-space: nowrap; padding: 0 2px;
        }}
        .comp-tilt {{
          font-size: 15px; color: var(--ink-primary); margin: 2px 0 4px;
        }}
        .comp-tilt .why {{ color: var(--ink-tertiary); font-size: 13.5px; }}

        /* 브라우저 저장소 통로(components/local_store)는 화면에 아무것도 안 그리는
           컴포넌트입니다. 그래도 Streamlit 이 iframe 자리를 잡아두기 때문에,
           그냥 두면 화면 맨 위와 맨 아래에 빈 칸이 생깁니다. */
        /* iframe 제목은 "components.local_store.etf_local_store" 처럼 모듈 경로가
           앞에 붙습니다. Streamlit 버전에 따라 달라질 수 있어 끝부분만 봅니다. */
        iframe[title$="etf_local_store"] {{
          height: 0 !important; min-height: 0 !important; display: block;
        }}
        [data-testid="stElementContainer"]:has(> iframe[title$="etf_local_store"]) {{
          height: 0; min-height: 0; margin: 0 !important; padding: 0 !important;
          overflow: hidden;
        }}

        /* 입력창 글자 */
        [data-testid="stTextInputField"], [data-testid="stNumberInputField"] {{
          font-size: 15px !important;
          color: var(--ink-primary) !important;
        }}

        /* 버튼 글자 */
        [data-testid="stBaseButton-secondary"] p,
        [data-testid="stBaseButton-primary"] p {{
          font-size: 14.5px !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
