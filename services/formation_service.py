"""
services/formation_service.py  --  자리에 뜻을 주기 (포메이션 · 주장 · 이름)
============================================================================

지금까지 전술판의 자리는 아무 뜻이 없었습니다 -- 빈 칸에 순서대로 꽂혔습니다.
그런데 **자리에 뜻을 주면 배치 자체가 설명이 됩니다.**

    공격(ST·AM)   커버드콜 · 리츠      많이 주지만 흔들리는 것
    미드필드(MC·DM) 배당주 · 지수        중심을 잡는 것
    수비(DF·GK)    채권 · 현금성        깨질 때 버티는 것

그러면 전술판을 보는 것만으로 **"내가 공격에 몰빵했구나"** 가 보입니다.
구성 막대(composition_service)와 같은 정보를, 이 앱만 할 수 있는 방식으로요.

⚠ 절대 자동으로 옮기지 않습니다
-------------------------------
사용자가 손으로 배치해둔 걸 앱이 마음대로 바꾸면 화가 납니다.
`tidy()` 는 **"포지션 자동 정리" 버튼을 눌렀을 때만** 불립니다.
"""

from __future__ import annotations

import pitch_grid
from formatting import won_short
from models.portfolio import Portfolio
from services import composition_service as cs

# 유형 -> 어느 라인에 둘 것인가. "자리에 뜻을 준다" 는 규칙이 여기 한 곳에 있습니다.
KIND_ROW = {
    cs.KIND_COVERED_CALL: "ST",     # 많이 주지만 가장 흔들림
    cs.KIND_REIT: "AM",             # 배당은 높고 변동도 있음
    cs.KIND_DIVIDEND: "MC",         # 중심
    cs.KIND_OTHER: "DM",            # 모르는 건 중앙 뒤쪽
    cs.KIND_BOND: "DF",             # 깨질 때 버티는 것
}
DEFAULT_ROW = "MC"

# 포메이션 표기에서 쓰는 묶음 (골키퍼는 축구처럼 숫자에서 뺍니다)
_GROUP_ROWS = {
    "공격": ("ST", "AM"),
    "미드필드": ("MC", "DM"),
    "수비": ("DF", "GK"),
}


def row_for(security) -> str:
    """이 종목이 갈 라인."""
    kind = cs.classify_kind(security.market, security.ticker, security.display_name)
    return KIND_ROW.get(kind, DEFAULT_ROW)


def counts(portfolio: Portfolio) -> dict[str, int]:
    """지금 배치 기준으로 공격/미드필드/수비에 몇 명인가.

    유형이 아니라 **실제로 놓인 자리**를 셉니다. 사용자가 손으로 옮겼으면 그게 맞습니다.
    """
    out = {"공격": 0, "미드필드": 0, "수비": 0}
    for sec in portfolio.securities:
        if not pitch_grid.is_slot(sec.slot):
            continue
        row = pitch_grid.split(sec.slot)[0]
        for group, rows in _GROUP_ROWS.items():
            if row in rows:
                out[group] += 1
                break
    return out


def formation(portfolio: Portfolio) -> str:
    """축구식 표기. 뒤에서부터 수비-미드-공격 (예: "2-2-1").

    0 이 들어가도 그대로 씁니다 -- "0-0-5" 는 **전부 공격에 있다**는 뜻이고,
    그게 이 표기의 쓸모입니다. 숨기면 볼 이유가 없어집니다.
    """
    c = counts(portfolio)
    if sum(c.values()) == 0:
        return ""
    return f"{c['수비']}-{c['미드필드']}-{c['공격']}"


def captain_id(portfolio: Portfolio) -> str | None:
    """비중이 가장 큰 종목. 전술판에 완장을 달아 "이 포트의 중심" 을 보이게 합니다."""
    holders = [s for s in portfolio.securities if s.target_weight > 0]
    if not holders:
        return None
    return max(holders, key=lambda s: (s.target_weight, s.id)).id


def tidy(portfolio: Portfolio) -> int:
    """유형에 맞는 라인으로 다시 배치합니다. 옮긴 종목 수를 돌려줍니다.

    ⚠ 버튼을 눌렀을 때만 부르세요. 자동으로 부르면 사용자가 손으로 맞춰둔 배치가
      말도 없이 흐트러집니다.

    비중이 큰 종목부터 중앙(C)에 가깝게 놓습니다. 한 라인이 꽉 차면 이웃 라인으로
    밀려나는데, 그건 pitch_grid.first_free_slot 이 알아서 합니다.
    """
    ordered = sorted(portfolio.securities, key=lambda s: (-s.target_weight, s.ticker))
    before = {s.id: s.slot for s in ordered}
    used: set[str] = set()
    for sec in ordered:
        target = pitch_grid.first_free_slot(used, row_for(sec))
        if target is None:
            continue
        used.add(target)
        sec.place_in_slot(target)
    return sum(1 for s in ordered if before.get(s.id) != s.slot)


def suggest_name(portfolio: Portfolio, comp=None) -> str:
    """담은 내용으로 전술 이름을 지어봅니다 (예: "1억 월배당 2-2-1").

    슬롯이 생기면서 이름 지을 일이 자주 생깁니다. "새 전술 (2)" 가 쌓이면
    슬롯이 무용지물이 되므로, 내용으로 기본 이름을 만들어 줍니다.
    """
    parts = [won_short(portfolio.initial_capital_krw)]
    if comp is not None:
        schedule = _dominant_schedule(comp)
        if schedule:
            parts.append(schedule)
    shape = formation(portfolio)
    if shape:
        parts.append(shape)
    return " ".join(p for p in parts if p)


def _dominant_schedule(comp) -> str:
    """담은 돈 기준으로 가장 큰 분배주기 한 덩어리."""
    for bar in cs.bars(comp):
        if bar.title == "언제 들어오나" and bar.slices:
            top = max(bar.slices, key=lambda s: s.pct)
            return top.label if top.label != cs.SCHEDULE_NONE else ""
    return ""
