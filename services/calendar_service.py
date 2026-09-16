"""
services/calendar_service.py  --  분배금 달력 (언제 얼마가 들어오나)
====================================================================

왜 이게 필요한가
----------------
"포트폴리오를 짠다" 는 한 번 하면 끝이지만, **"이번 달 얼마 들어오지"** 는 매달
궁금합니다. 이 앱에서 매달 다시 열어볼 이유가 되는 몇 안 되는 화면입니다.

새 데이터를 받아오지 않습니다
-----------------------------
`portfolio_service.compute()` 가 이미 종목마다 **지난 12개월 지급 이력**
(`RowResult.distribution_payments` = [(지급일, 주당 금액), ...]) 을 들고 있습니다.
지금은 그걸 합쳐서 "월 얼마" 라는 숫자 하나로만 쓰는데, 달력은 **같은 데이터를
날짜별로 펴서 보여주는 것**뿐입니다. 그래서 달을 아무리 넘겨도 호출이 0번입니다.

지나간 달과 다가올 달은 성격이 다릅니다
---------------------------------------
    지나간 달 : 그 달에 **실제로 지급된** 기록
    이번 달·다음 달 : 작년 같은 달 기록으로 **미뤄본 값** (예상)

여기에 함정이 하나 있습니다 -- **그때 이 종목을 갖고 있었는지는 우리가 모릅니다.**
수량은 지금 담은 수량이므로, 지나간 달도 "이만큼 받으셨습니다" 가 아니라
**"지금 이 구성이었다면 이만큼"** 이라고 말해야 합니다. 화면 문구가 그렇게 돼 있고,
`MonthPlan.basis` 가 그 구분을 들고 다닙니다.
"""

from __future__ import annotations

import calendar as _calendar
from dataclasses import dataclass, field
from datetime import date

import config
from models.security import MARKET_KR

# 앞뒤로 몇 달까지 넘겨볼 수 있는가. 지급 이력이 12개월치뿐이라 그 밖은 근거가 없습니다.
# 더 넓히면 숫자를 지어내는 것이 됩니다.
MONTH_RANGE = 12

BASIS_ACTUAL = "actual"      # 그 달에 실제로 지급된 기록
BASIS_FORECAST = "forecast"  # 작년 같은 달 기록으로 미뤄본 값


@dataclass(frozen=True)
class PayEntry:
    day: date
    ticker: str
    label: str            # 화면에 쓸 이름 (한국은 종목명, 미국은 티커)
    amount_krw: float


@dataclass
class MonthPlan:
    year: int
    month: int
    basis: str                              # BASIS_ACTUAL | BASIS_FORECAST
    entries: list[PayEntry] = field(default_factory=list)
    silent: list[str] = field(default_factory=list)   # 이 달에 지급이 없는 종목
    in_range: bool = True                   # 이력으로 커버되는 달인가
    fx_missing: bool = False                # 환율이 없어 미국 종목을 못 넣었는가

    @property
    def total_krw(self) -> float:
        return sum(e.amount_krw for e in self.entries)

    @property
    def title(self) -> str:
        """예: "2026년 9월 예상 (세전)"

        **세전이라고 제목에 박아둡니다.** 이 화면은 "이번 달에 얼마 들어오나" 를 보는
        곳이라, 사람들이 통장에 찍힐 금액으로 읽습니다. 실제로는 배당소득세를 떼고
        들어오므로 그대로 믿으면 어긋납니다. 밑에 작게 적으면 안 읽히고,
        그림으로 퍼질 때는 더더욱 안 읽힙니다. 제목에 붙여야 같이 다닙니다.
        """
        suffix = "예상" if self.basis == BASIS_FORECAST else "실제 지급 기준"
        return f"{self.year}년 {self.month}월 {suffix} (세전)"


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    """(년, 월) 에서 delta 달만큼 옮긴 (년, 월)."""
    index = (year * 12 + (month - 1)) + delta
    return index // 12, index % 12 + 1


def months_between(a: tuple[int, int], b: tuple[int, int]) -> int:
    """a 에서 b 까지 몇 달 차이인가 (b 가 뒤면 양수)."""
    return (b[0] * 12 + b[1]) - (a[0] * 12 + a[1])


def _clamp_day(year: int, month: int, day: int) -> date:
    """작년 3월 31일을 올해 2월로 옮길 때처럼, 없는 날짜는 그 달 마지막 날로."""
    last = _calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last))


def _label(security) -> str:
    """한국 종목은 이름, 미국은 티커. (표의 '종목' 칸과 같은 규칙)"""
    if security.market == MARKET_KR:
        return security.display_name or security.ticker
    return security.ticker or security.display_name


def month_plan(comp, year: int, month: int, *, today: date | None = None) -> MonthPlan:
    """그 달에 들어올(또는 들어왔던) 분배금을 종목별로 펼칩니다.

    comp 는 portfolio_service.compute() 결과입니다. **여기서 네트워크를 쓰지 않습니다.**
    """
    today = today or config.today_local()
    now = (today.year, today.month)
    target = (year, month)
    offset = months_between(now, target)

    # 이번 달을 포함한 앞으로는 "예상", 지나간 달은 "실제 지급 기준".
    # 이번 달은 이미 지급된 것도 있지만, 한 달 안에서 실제와 예상을 섞으면 어느 줄이
    # 어느 쪽인지 알 수 없게 됩니다. 달 단위로 딱 갈라서 말합니다.
    basis = BASIS_FORECAST if offset >= 0 else BASIS_ACTUAL
    plan = MonthPlan(year=year, month=month, basis=basis)

    if abs(offset) > MONTH_RANGE:
        plan.in_range = False
        return plan

    # 예상이면 작년 같은 달 기록을 봅니다. 실제면 그 달 자체를 봅니다.
    source_year = year - 1 if basis == BASIS_FORECAST else year

    # 환율이 없으면 미국 종목은 수량조차 계산되지 않아서(원화 가격을 모름) 아래 반복에
    # 아예 안 걸립니다. 그래서 여기서 미리 확인해야 "왜 미국 종목이 안 보이지?" 에
    # 답할 수 있습니다. 반복 안에서 보면 영원히 False 인 죽은 검사가 됩니다.
    if not comp.usdkrw and any(r.currency == "USD" and r.distribution_included
                               for r in comp.rows):
        plan.fx_missing = True

    for row in comp.rows:
        if not row.distribution_included or row.shares <= 0:
            continue
        rate = float(comp.usdkrw) if row.currency == "USD" else 1.0
        if rate <= 0:
            continue

        found = False
        for pay_date, per_share in row.distribution_payments:
            if pay_date.year != source_year or pay_date.month != month:
                continue
            amount = float(per_share) * float(row.shares) * rate
            if amount <= 0:
                continue
            plan.entries.append(PayEntry(
                day=_clamp_day(year, month, pay_date.day),
                ticker=row.security.ticker,
                label=_label(row.security),
                amount_krw=amount,
            ))
            found = True
        if not found:
            plan.silent.append(_label(row.security))

    plan.entries.sort(key=lambda e: (e.day, -e.amount_krw))
    return plan


def capture_rows(plan: MonthPlan) -> list[dict]:
    """달력을 **이미지로 그릴 때** 쓰는 모양 (components/table_capture).

    합계 줄을 맨 아래에 붙입니다. 공유된 그림만 보는 사람은 앱의 큰 숫자를 못 보니까요.
    """
    from formatting import won

    out = [{"cells": [{"t": f"{e.day:%m/%d}"}, {"t": e.label}, {"t": won(e.amount_krw)}]}
           for e in plan.entries]
    if out:
        out[-1]["sep"] = True
    out.append({"cells": [{"t": "합계"}, {"t": ""}, {"t": won(plan.total_krw)}]})
    return out


def capture_notes(plan: MonthPlan) -> list[str]:
    """그림 아래 붙일 안내. **화면과 같은 말**이어야 합니다.

    특히 "예상" 과 "지금 이 구성이었다면" 은 그림에서 더 중요합니다 --
    그림은 앱 밖으로 퍼지는데, 거기엔 앞뒤 맥락이 없습니다.
    """
    notes = []
    if plan.basis == BASIS_FORECAST:
        notes.append("지난 12개월 지급 패턴으로 만든 예상입니다. "
                     "실제 지급일·금액은 달라질 수 있습니다.")
    else:
        notes.append("그 달에 실제로 지급된 금액입니다. 다만 수량은 지금 담은 것 "
                     "기준이라, '지금 이 구성이었다면' 이만큼이라는 뜻입니다.")
    if plan.silent:
        notes.append("이 달 지급 없음 — " + " · ".join(plan.silent))
    return notes


def can_go(comp, year: int, month: int, delta: int, *, today: date | None = None) -> bool:
    """그 방향으로 한 달 더 넘어갈 수 있는가 (이력 범위 안인가)."""
    today = today or config.today_local()
    y, m = shift_month(year, month, delta)
    return abs(months_between((today.year, today.month), (y, m))) <= MONTH_RANGE
