"""
components/table_capture/  --  표를 "공유할 수 있는 그림" 으로 (📸 복사 / 💾 저장)

전술판에만 있던 이미지 복사·저장을 **표에도** 붙입니다.
비교표 · 분배금 달력 · 백테스트 결과가 이 컴포넌트 하나를 나눠 씁니다.

왜 화면을 찍지 않고 다시 그리나
-------------------------------
화면을 그대로 찍으려면 외부 라이브러리를 얹어야 하고, Streamlit 이 화면 구조를
바꾸면 조용히 깨집니다. 전술판이 이미 **캔버스에 직접 그리는** 방식으로 잘 돌고
있어서 같은 방식을 씁니다. 결과도 더 낫습니다 -- 버튼이나 스크롤바 같은 화면
부속이 안 들어가고, 공유용으로 여백·글자 크기를 따로 잡을 수 있습니다.

쓰는 법
-------
    table_capture(
        title="두 전술 비교",
        subtitle="2026-09-16 기준",
        sections=[{
            "heading": "",                          # 표가 하나뿐이면 생략
            "columns": ["", "현재안", "공격안"],     # 첫 칸은 항목 이름 열
            "rows": [{"cells": [{"t": "월 분배금"},
                                {"t": "30.9만", "bar": 25},
                                {"t": "123만", "win": True, "bar": 100}]}],
        }],
        notes=["초록은 ... 줄에만 칠합니다."],
        filename="ETF_MANAGER_2027_비교_20260916.png",
        key="cmp_cap",
    )

왜 표가 여러 개인가 (sections)
------------------------------
백테스트 화면은 **요약 + 종목별** 두 덩어리입니다. 요약만 그림에 담으면
"무엇을 담았길래 그런 결과가 나왔는지" 가 빠져서, 숫자만 있고 근거가 없는
그림이 됩니다. 화면에서 보이는 것이 그대로 그림에 들어가야 합니다.

셀에 줄 수 있는 것
------------------
    t     화면에 찍을 글자 (필수)
    win   True 면 초록 굵게 -- **"많을수록 원하던 것" 인 줄에만** 쓰세요.
          그 외의 줄에 쓰면 색이 곧 추천이 됩니다.
    dim   True 면 흐리게 (부차적인 값)
    bar   0~100. 값 아래 얇은 막대. 몇 배 차이인지 즉시 보이게 합니다.

줄에 `"sep": True` 를 주면 그 줄 **아래**에 진한 구분선을 긋습니다.
"""

from __future__ import annotations

import os

import streamlit.components.v1 as components

_FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")

_component_func = components.declare_component("etf_table_capture", path=_FRONTEND_DIR)


def table_capture(*, title: str = "", subtitle: str = "",
                  sections: list[dict] | None = None,
                  notes: list[str] | None = None,
                  footer: str = "",
                  filename: str = "etf-manager.png",
                  key: str | None = None):
    """표(하나 이상)를 이미지로 복사·저장하는 버튼 두 개를 그립니다."""
    return _component_func(
        title=title,
        subtitle=subtitle,
        sections=sections or [],
        notes=notes or [],
        footer=footer,
        filename=filename,
        key=key,
        default=None,
    )
