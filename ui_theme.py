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
