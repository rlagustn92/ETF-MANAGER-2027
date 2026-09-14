"""
components/football_pitch/  --  FM 풍 세로 전술판 (포지션 슬롯 스냅, 인수인계서 7~14)
==============================================================================

Streamlit Custom Component (빌드 불필요, 정적 프론트엔드 + 인라인 JS).
- 세로 방향. 화면 아래 = 우리 진영(골키퍼), 화면 위 = 공격 방향.
- 종목 카드를 잡아서 포지션 슬롯으로 옮기면 그 슬롯에 스냅됩니다 (FM 방식).
  한 슬롯에는 한 종목. 이미 다른 종목이 있으면 서로 자리를 바꿉니다(스왑).
- 슬롯 격자(5칸 x 6라인)는 pitch_grid.py 에서 정의합니다.
- 카드 크기는 비중과 무관하게 모두 동일. (인수인계서 14)

이 컴포넌트만 고치면 전술판 UI 를 바꿀 수 있습니다. (인수인계서 107-1, 124)

반환값
------
dict {
  "assignments": { security_id: slot_id, ... },   # 드래그 후 슬롯 배치
  "selected_id": str | None,
  "nonce": int,
}
또는 최초 렌더 시 None.
"""

from __future__ import annotations

import os

import streamlit.components.v1 as components

_FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")

_component_func = components.declare_component("etf_football_pitch", path=_FRONTEND_DIR)


def football_pitch(
    players: list[dict],
    slots: list[dict],
    *,
    selected_id: str | None = None,
    height: int = 720,
    aspect_ratio: float = 96 / 72,
    compact: bool = False,
    summary: dict | None = None,
    legend: list[dict] | None = None,
    footer: str = "",
    capture_filename: str = "",
    comment_text: str = "",
    key: str | None = None,
):
    """세로 전술판 컴포넌트.

    players: [{ "id", "ticker", "display_name", "market"("US"|"KR"),
                "label",        # 이름표 글자 (pitch_kit.card_label 로 줄인 것)
                "kit",          # 유니폼 색 (pitch_kit.kit_of)
                "weight_pct",   # 등번호로 찍힘
                "slot", "has_warning" }, ...]
    slots:   pitch_grid.slot_meta()  -> [{ "id","row","col","x","y","label","group" }, ...]
    aspect_ratio: 전술판 세로/가로 비율 (기본 96/72). 작을수록 짧고 납작해짐 -- 레이아웃 실험용.
    compact: True 면 카드/라벨 글씨를 살짝 축소 -- 레이아웃 실험용.

    summary / legend / footer 는 **화면에는 안 나오고 📸 캡처 이미지에만** 구워집니다.
    전술판만 캡처하면 "그래서 얼마 버는데?" 가 안 보여서 공유해도 감이 안 온다는
    피드백에서 나온 기능입니다 (사용자 요청).
        summary: {"cells": [{"k": 라벨, "v": 값}, ...], "note": 고지, "key_note": 범례 한 줄}
        legend:  [{"name": 정식 종목명, "amount": "30% · 1,350만 · 월 5.6만",
                   "color": 유니폼 색, "us": bool}, ...]
        footer:  "⚽ ETF MANAGER 2027 · etfmanager2027.streamlit.app"

    capture_filename 은 💾 저장 버튼이 내려받을 PNG 파일 이름입니다
    (config.capture_image_filename). 저장 **위치**는 지정할 수 없습니다 --
    브라우저 보안상 무조건 그 브라우저의 다운로드 폴더로 갑니다.

    comment_text 는 📋 텍스트 버튼이 클립보드에 넣을 글자입니다(app.comment_text).
    비어 있으면 그 버튼을 숨깁니다.
    """
    return _component_func(
        players=players,
        slots=slots,
        selected_id=selected_id,
        height=height,
        aspect_ratio=aspect_ratio,
        compact=compact,
        summary=summary,
        legend=legend or [],
        footer=footer,
        capture_filename=capture_filename,
        comment_text=comment_text,
        key=key,
        default=None,
    )
