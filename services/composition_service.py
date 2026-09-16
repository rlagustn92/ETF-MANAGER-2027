"""
services/composition_service.py  --  "내가 뭘 담았나" 를 3초 만에 보이게
=======================================================================

이 앱의 대원칙은 "쉽고 직관적이게 포트폴리오를 만들고 **그 방향성을 넣는다**" 입니다.
표를 읽는 것과 막대 세 줄을 보는 것은 전혀 다릅니다.

    어느 나라   미국 60% / 한국 40%
    어떤 종류   배당주 45% / 커버드콜 35% / 채권 20%
    언제 들어오나  월배당 70% / 분기 30%

세 번째 줄이 특히 쓸모 있습니다 -- **분기배당만 담으면 세 달 중 두 달은 0원**인데,
대부분 짜고 나서야 압니다.

⚠ 평가가 아니라 거울입니다
--------------------------
성향 라벨("공격형에 가깝습니다")은 점수도 등급도 아닙니다. 담은 것을 그대로 되비추는
문장이고, **왜 그렇게 봤는지**를 항상 같이 적습니다. 그래야 사용자가 동의하든 말든
스스로 판단할 수 있습니다. "빼세요/담으세요" 는 쓰지 않습니다.

분류를 어떻게 하나 -- 두 가지 방식이 섞여 있습니다
--------------------------------------------------
    분배주기 : **데이터로** 셉니다. 최근 12개월에 몇 번 지급했는지 세면 끝이라
               사전이 필요 없고 새 종목도 자동으로 맞습니다.
    유형     : **이름으로** 봅니다. 여기엔 사전이 필요하고, 사전에 없으면
               "기타" 로 둡니다. 모르는 걸 아는 척하지 않습니다.
"""

from __future__ import annotations

from dataclasses import dataclass

from models.security import MARKET_KR

# ---------------------------------------------------------------------
# 유형 분류
# ---------------------------------------------------------------------
KIND_COVERED_CALL = "커버드콜"
KIND_BOND = "채권"
KIND_REIT = "리츠·인프라"
KIND_DIVIDEND = "배당주"
KIND_OTHER = "기타"

# 한국 ETF 는 이름에 성격이 그대로 들어 있어서 이름만 봐도 거의 다 맞습니다.
_KR_NAME_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("커버드콜", "타겟위클리", "프리미엄인컴"), KIND_COVERED_CALL),
    (("채권", "국채", "회사채", "통안", "단기자금", "머니마켓", "CD금리", "KOFR"), KIND_BOND),
    (("리츠", "인프라", "부동산"), KIND_REIT),
    (("배당", "고배당", "다우존스"), KIND_DIVIDEND),
)

# 미국은 티커가 곧 이름이라 사전이 필요합니다. 사람들이 실제로 담는 것 위주로 적습니다.
# ⚠ 여기 없는 티커는 "기타" 가 됩니다. 그게 맞습니다 -- 모르면 모른다고 해야 합니다.
_US_TICKER_KINDS: dict[str, str] = {
    # 커버드콜 / 옵션 인컴
    "JEPI": KIND_COVERED_CALL, "JEPQ": KIND_COVERED_CALL, "QYLD": KIND_COVERED_CALL,
    "XYLD": KIND_COVERED_CALL, "RYLD": KIND_COVERED_CALL, "QQQI": KIND_COVERED_CALL,
    "SPYI": KIND_COVERED_CALL, "DIVO": KIND_COVERED_CALL, "JEPY": KIND_COVERED_CALL,
    "TLTW": KIND_COVERED_CALL, "QDTE": KIND_COVERED_CALL, "XDTE": KIND_COVERED_CALL,
    # 채권
    "TLT": KIND_BOND, "IEF": KIND_BOND, "SHY": KIND_BOND, "BND": KIND_BOND,
    "AGG": KIND_BOND, "LQD": KIND_BOND, "HYG": KIND_BOND, "TIP": KIND_BOND,
    "SGOV": KIND_BOND, "BIL": KIND_BOND, "VCIT": KIND_BOND, "VCSH": KIND_BOND,
    # 리츠·인프라
    "O": KIND_REIT, "VNQ": KIND_REIT, "SCHH": KIND_REIT, "REET": KIND_REIT,
    "AMT": KIND_REIT, "PLD": KIND_REIT, "STAG": KIND_REIT, "MAIN": KIND_REIT,
    # 배당주 / 지수
    "SCHD": KIND_DIVIDEND, "VYM": KIND_DIVIDEND, "DGRO": KIND_DIVIDEND,
    "VIG": KIND_DIVIDEND, "HDV": KIND_DIVIDEND, "DVY": KIND_DIVIDEND,
    "SPYD": KIND_DIVIDEND, "VOO": KIND_DIVIDEND, "SPY": KIND_DIVIDEND,
    "IVV": KIND_DIVIDEND, "QQQ": KIND_DIVIDEND, "QQQM": KIND_DIVIDEND,
    "VTI": KIND_DIVIDEND, "VT": KIND_DIVIDEND,
}


def classify_kind(market: str, ticker: str, display_name: str = "") -> str:
    """이 종목이 어떤 종류인가. 모르면 KIND_OTHER."""
    if market == MARKET_KR:
        name = (display_name or "").replace(" ", "")
        for keywords, kind in _KR_NAME_RULES:
            if any(k.replace(" ", "") in name for k in keywords):
                return kind
        return KIND_OTHER
    return _US_TICKER_KINDS.get((ticker or "").strip().upper(), KIND_OTHER)


# ---------------------------------------------------------------------
# 분배주기 분류 (데이터로 셉니다 -- 사전 없음)
# ---------------------------------------------------------------------
SCHEDULE_WEEKLY = "주배당"
SCHEDULE_MONTHLY = "월배당"
SCHEDULE_QUARTERLY = "분기배당"
SCHEDULE_RARE = "연 1~2회"
SCHEDULE_NONE = "분배 없음"


def classify_schedule(n_payments_ttm: int) -> str:
    """최근 12개월 지급 횟수로 주기를 봅니다. 새로 나온 종목도 자동으로 맞습니다."""
    n = int(n_payments_ttm or 0)
    if n >= 40:
        return SCHEDULE_WEEKLY
    if n >= 10:
        return SCHEDULE_MONTHLY
    if n >= 3:
        return SCHEDULE_QUARTERLY
    if n >= 1:
        return SCHEDULE_RARE
    return SCHEDULE_NONE


# ---------------------------------------------------------------------
# 막대 만들기
# ---------------------------------------------------------------------
@dataclass(frozen=True)
class Slice:
    label: str
    pct: float          # 담은 돈 기준 비율 (합계 100)


@dataclass(frozen=True)
class Bar:
    title: str
    slices: tuple[Slice, ...]


def _mix(pairs: list[tuple[str, float]], order: list[str] | None = None) -> tuple[Slice, ...]:
    """(라벨, 금액) 목록을 비율 막대로. 금액 합이 0 이면 빈 막대."""
    total = sum(amount for _, amount in pairs if amount > 0)
    if total <= 0:
        return ()
    merged: dict[str, float] = {}
    for label, amount in pairs:
        if amount > 0:
            merged[label] = merged.get(label, 0.0) + amount
    items = list(merged.items())
    if order:
        items.sort(key=lambda kv: (order.index(kv[0]) if kv[0] in order else len(order),
                                   -kv[1]))
    else:
        items.sort(key=lambda kv: -kv[1])
    return tuple(Slice(label=k, pct=v / total * 100.0) for k, v in items)


def bars(comp) -> list[Bar]:
    """전술판 아래에 그릴 막대 세 줄. **담은 돈 기준**이라 합계가 100% 입니다.

    남긴 현금은 여기 안 들어갑니다 -- 요약 바의 '잔여현금' 이 이미 말해줍니다.
    여기서 묻는 건 "담은 것끼리의 구성" 입니다.
    """
    invested = [(r, r.actual_investment_krw) for r in comp.rows
                if r.actual_investment_krw > 0]
    if not invested:
        return []

    country = _mix([("미국" if r.security.market != MARKET_KR else "한국", amount)
                    for r, amount in invested], order=["미국", "한국"])
    kind = _mix([(classify_kind(r.security.market, r.security.ticker,
                                r.security.display_name), amount)
                 for r, amount in invested],
                order=[KIND_DIVIDEND, KIND_COVERED_CALL, KIND_REIT, KIND_BOND, KIND_OTHER])
    schedule = _mix([(classify_schedule(r.distribution_n_payments), amount)
                     for r, amount in invested],
                    order=[SCHEDULE_WEEKLY, SCHEDULE_MONTHLY, SCHEDULE_QUARTERLY,
                           SCHEDULE_RARE, SCHEDULE_NONE])
    out = [Bar("어느 나라", country), Bar("어떤 종류", kind), Bar("언제 들어오나", schedule)]
    return [b for b in out if b.slices]


def share_of(comp, kind: str) -> float:
    """담은 돈 중 그 종류가 차지하는 비율(%)."""
    for bar in bars(comp):
        if bar.title != "어떤 종류":
            continue
        for s in bar.slices:
            if s.label == kind:
                return s.pct
    return 0.0


# ---------------------------------------------------------------------
# 성향 라벨 (평가가 아니라 거울)
# ---------------------------------------------------------------------
# 커버드콜은 옵션 프리미엄으로 분배금을 만듭니다. 분배율이 높은 대신 오를 때 덜 먹고
# 가격 변동이 큽니다. presets.py 가 예시를 안정/보통/공격으로 나눈 기준과 같습니다.
TILT_AGGRESSIVE_AT = 50.0
TILT_BALANCED_AT = 20.0


def tilt(comp) -> tuple[str, str] | None:
    """(문장, 근거). 담은 게 없으면 None.

    ⚠ "~에 가깝습니다" 라는 말투를 지켜주세요. 단정하면 평가가 되고, 평가는 추천이 됩니다.
    """
    if not bars(comp):
        return None
    cc = share_of(comp, KIND_COVERED_CALL)
    if cc >= TILT_AGGRESSIVE_AT:
        label = "공격형에 가깝습니다"
    elif cc >= TILT_BALANCED_AT:
        label = "보통형에 가깝습니다"
    else:
        label = "안정형에 가깝습니다"
    return label, f"커버드콜 비중이 {cc:.0f}% 라서요."
