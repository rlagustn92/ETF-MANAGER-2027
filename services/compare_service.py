"""
services/compare_service.py  --  두 전술 나란히 놓고 보기
=========================================================

"뭐가 더 낫지?" 는 사람을 아주 오래 붙잡는 질문입니다. 슬롯이 생겼으니
저장된 두 전술을 계산해서 표 두 줄로 놓기만 하면 됩니다.

⚠ 색으로 추천하지 않습니다
--------------------------
분배금이 많은 쪽을 초록으로 칠하는 건 괜찮습니다 -- 사용자가 "월 얼마" 를 보려고
온 거니까요. 그런데 **커버드콜 비중이나 종목 수는 높다고 좋은 게 아닙니다.**
그런 줄까지 색칠하면 색이 곧 추천이 됩니다. 그래서 각 줄이 "이 줄은 색칠해도
되는가" 를 직접 들고 다닙니다(CompareRow.higher_is_what_you_asked_for).

⚠ 계산은 창을 열 때만
---------------------
B 전술도 가격을 조회해야 합니다. 겹치는 종목은 캐시가 살아 있어 거의 공짜지만,
완전히 다른 7종목이면 7번 호출입니다. **첫 화면에서 자동으로 돌면 안 되고**,
비교를 누른 순간에만 돌아야 합니다. 그래야 평소 화면 속도가 그대로입니다.
"""

from __future__ import annotations

from dataclasses import dataclass

from formatting import pct, won_short
from models.security import MARKET_KR
from services import composition_service


# 비교 드롭다운의 "아직 안 골랐음" 값. 창을 닫을 때 여기로 되돌려놓지 않으면
# 고른 값이 남아서 **창이 닫히자마자 다시 열립니다.**
# app.py 와 테스트가 같은 값을 보도록 여기 한 곳에 둡니다.
# 비교 버튼에 들어갈 수 있는 이름 길이.
BUTTON_NAME_MAX = 11


def button_label(name: str) -> str:
    """비교 버튼 글자. 예: "⇄ 공격배당형 예시 비교"

    조사("○○ **과** 비교")를 안 씁니다. 받침이 없는 이름에는 "와" 가 맞아서
    **"예시 과 비교"** 처럼 틀린 말이 나오기 때문입니다. 조사를 맞추는 것보다
    아예 빼는 쪽이 안전하고 짧습니다.
    """
    short = (name or "전술").strip() or "전술"
    if len(short) > BUTTON_NAME_MAX:
        short = short[:BUTTON_NAME_MAX].rstrip(" ·-_,") + "…"
    return f"⇄ {short} 비교"


@dataclass(frozen=True)
class CompareRow:
    label: str
    a_text: str
    b_text: str
    # 이 줄에서 큰 쪽이 "사용자가 원한 것" 인가. False 면 색칠하지 않습니다.
    higher_is_what_you_asked_for: bool = False
    a_value: float = 0.0
    b_value: float = 0.0

    @property
    def winner(self) -> str | None:
        """색칠할 쪽. 색칠하면 안 되는 줄이거나 비기면 None."""
        if not self.higher_is_what_you_asked_for:
            return None
        if abs(self.a_value - self.b_value) < 1e-9:
            return None
        return "a" if self.a_value > self.b_value else "b"

    @property
    def bars(self) -> tuple[float, float] | None:
        """두 값의 상대 크기(0~100). 막대를 그릴 수 없는 줄이면 None.

        왜 막대를 그리나
        ----------------
        "124만" 과 "41.7만" 을 나란히 놓아도 **몇 배인지는 한 번 계산해야** 압니다.
        얇은 막대 하나면 3배쯤이라는 게 즉시 보입니다. 장식이 아니라 비교를 빠르게
        하는 장치라서, **비교해도 되는 줄(분배금·분배율)에만** 붙입니다.

        음수가 섞이면(잔여현금 등) 길이 비유가 깨지므로 그리지 않습니다.
        """
        if not self.higher_is_what_you_asked_for:
            return None
        a, b = float(self.a_value), float(self.b_value)
        if a < 0 or b < 0:
            return None
        top = max(a, b)
        if top <= 0:
            return None
        return a / top * 100.0, b / top * 100.0


def _holdings(comp) -> dict[tuple[str, str], str]:
    """(시장, 종목코드) -> 화면에 쓸 이름."""
    out = {}
    for row in comp.rows:
        sec = row.security
        name = sec.display_name if sec.market == MARKET_KR else sec.ticker
        out[(sec.market, sec.ticker)] = name or sec.ticker
    return out


def overlap(a_comp, b_comp) -> list[str]:
    """두 전술에 **둘 다** 들어 있는 종목 이름."""
    a, b = _holdings(a_comp), _holdings(b_comp)
    return sorted(a[k] for k in a.keys() & b.keys())


def rows(a_comp, b_comp) -> list[CompareRow]:
    """표에 그릴 줄들."""
    def cc(comp) -> float:
        return composition_service.share_of(comp, composition_service.KIND_COVERED_CALL)

    return [
        CompareRow("월 분배금",
                   won_short(a_comp.monthly_distribution_krw),
                   won_short(b_comp.monthly_distribution_krw),
                   True,
                   a_comp.monthly_distribution_krw, b_comp.monthly_distribution_krw),
        CompareRow("연 분배금",
                   won_short(a_comp.annual_distribution_krw),
                   won_short(b_comp.annual_distribution_krw),
                   True,
                   a_comp.annual_distribution_krw, b_comp.annual_distribution_krw),
        CompareRow("투자금 대비 분배율",
                   pct(a_comp.income_yield_on_invested_pct),
                   pct(b_comp.income_yield_on_invested_pct),
                   True,
                   a_comp.income_yield_on_invested_pct,
                   b_comp.income_yield_on_invested_pct),
        # 아래부터는 **높다고 좋은 게 아닙니다.** 색칠하지 않습니다.
        CompareRow("종목 수", str(len(a_comp.rows)), str(len(b_comp.rows)),
                   False, len(a_comp.rows), len(b_comp.rows)),
        CompareRow("커버드콜 비중", pct(cc(a_comp), 0), pct(cc(b_comp), 0),
                   False, cc(a_comp), cc(b_comp)),
        CompareRow("총 원금", won_short(a_comp.total_actual_investment_krw),
                   won_short(b_comp.total_actual_investment_krw),
                   False,
                   a_comp.total_actual_investment_krw,
                   b_comp.total_actual_investment_krw),
        CompareRow("남은 현금", won_short(a_comp.cash_balance_krw),
                   won_short(b_comp.cash_balance_krw),
                   False, a_comp.cash_balance_krw, b_comp.cash_balance_krw),
    ]


def capture_rows(a_comp, b_comp) -> list[dict]:
    """비교표를 **이미지로 그릴 때** 쓰는 모양 (components/table_capture).

    화면과 **같은 규칙**이어야 합니다 -- 초록과 막대는 "많을수록 원하던 것" 인 줄에만.
    화면에서는 안 칠하는데 그림에서는 칠하면, 공유된 그림이 앱보다 더 단정적으로
    보이게 됩니다.
    """
    out: list[dict] = []
    all_rows = rows(a_comp, b_comp)
    for i, row in enumerate(all_rows):
        win = row.winner
        bars = row.bars
        cells = [{"t": row.label}]
        for side, text in (("a", row.a_text), ("b", row.b_text)):
            cell: dict = {"t": text}
            if win == side:
                cell["win"] = True
            if bars:
                cell["bar"] = bars[0] if side == "a" else bars[1]
            cells.append(cell)
        # "많을수록 원하던 것" 줄과 그냥 사실인 줄 사이에 진한 선
        sep = (i + 1 < len(all_rows)
               and row.higher_is_what_you_asked_for
               and not all_rows[i + 1].higher_is_what_you_asked_for)
        out.append({"cells": cells, "sep": sep})
    return out


def goal_progress_line(a_comp, b_comp, goal_monthly_krw: float) -> str:
    """목표가 있으면 "이쪽으로 바꾸면 몇 % 가 되는가" 한 줄. 없으면 빈 문자열.

    목표가 전술이 아니라 **사람의 것**이라서 이 비교가 성립합니다.
    """
    if not goal_monthly_krw or goal_monthly_krw <= 0:
        return ""
    a = a_comp.monthly_distribution_krw / goal_monthly_krw * 100.0
    b = b_comp.monthly_distribution_krw / goal_monthly_krw * 100.0
    return (f"목표({won_short(goal_monthly_krw)}) 기준 "
            f"{a:.0f}% → {b:.0f}%")
