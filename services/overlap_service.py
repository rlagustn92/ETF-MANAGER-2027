"""
services/overlap_service.py  --  "분산한 줄 알았는데 사실 한 종목" 을 알려주기
==============================================================================

나스닥100 커버드콜을 세 개 담아놓고 분산했다고 생각하는 경우가 굉장히 많습니다.
이 앱의 대원칙("방향성을 넣는다")이 바로 이겁니다 -- 평가해주는 게 아니라
**자기가 뭘 담았는지 보이게** 해주는 것.

왜 이름으로는 못 잡나
---------------------
이름 비교는 **정확히 반대로 틀립니다.**

    VOO 와 SPY                     글자가 하나도 안 겹침  →  사실은 같은 물건
    TIGER 미국배당다우존스 vs
    TIGER 미국나스닥100커버드콜      앞부분이 잔뜩 겹침    →  사실은 다른 물건

봐야 하는 건 이름이 아니라 **이 ETF 가 무슨 지수를 따라가는가** 입니다.
그래서 여기에 대응표를 직접 적습니다.

⚠ 표에 없으면 "확인 못 함" 입니다
---------------------------------
표에 없는 종목을 조용히 빼놓고 "겹치는 것 없음" 이라고 하면 그게 거짓말입니다.
**"확인 못 함" 과 "안 겹침" 은 다른 말**이고, 화면에 그렇게 써야 합니다.
그리고 "빼세요/담으세요" 는 쓰지 않습니다 -- 사실만 보여주고 판단은 사용자 몫입니다.

가격으로 알아내는 방법(상관계수)도 있지만 종목마다 1년치 시세가 필요해서
첫 화면에 넣으면 느려집니다. 표만으로 흔한 경우는 거의 다 잡히므로 표로 갑니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from models.security import MARKET_KR

# ---------------------------------------------------------------------
# 기초지수 대응표
# ---------------------------------------------------------------------
# ⚠ **확신하는 것만** 적습니다. 애매한 걸 끼워 넣으면 "겹친다" 는 거짓 경고가 되고,
#   그건 경고가 아예 없는 것보다 나쁩니다. 애매하면 빼두면 "확인 못 함" 으로 나옵니다.
#   (국내 코드는 이 앱의 예시 구성에서 실제로 조회되는 것들입니다)
INDEX_OF: dict[tuple[str, str], str] = {}


def _register(index_name: str, us: tuple[str, ...] = (), kr: tuple[str, ...] = ()) -> None:
    for t in us:
        INDEX_OF[("US", t)] = index_name
    for t in kr:
        INDEX_OF[(MARKET_KR, t)] = index_name


# S&P500 계열 -- 그냥 추종하는 것과 커버드콜을 같이 둡니다.
# 기초가 같으면 같이 움직이기 때문입니다(커버드콜은 덜 오르고 같이 빠집니다).
_register("S&P500 계열",
          us=("SPY", "VOO", "IVV", "SPLG", "XYLD", "SPYI", "JEPI"))

_register("나스닥100 계열",
          us=("QQQ", "QQQM", "JEPQ", "QYLD", "QQQI"),
          kr=("441680",))                      # TIGER 미국나스닥100커버드콜(합성)

_register("다우존스 배당100 계열",
          us=("SCHD",),
          kr=("458730",                        # TIGER 미국배당다우존스
              "458760"))                       # TIGER 미국배당다우존스타겟커버드콜2호

_register("코스피200 계열",
          kr=("069500",                        # KODEX 200
              "102110",                        # TIGER 200
              "0219E0",                        # KODEX 200커버드콜액티브
              "498400"))                       # KODEX 200타겟위클리커버드콜

_register("미국 장기국채",
          us=("TLT", "EDV", "VGLT"))


@dataclass
class OverlapGroup:
    index_name: str
    members: list[tuple[str, float]] = field(default_factory=list)   # (이름, 비중%)

    @property
    def total_pct(self) -> float:
        return sum(w for _, w in self.members)


@dataclass
class OverlapReport:
    groups: list[OverlapGroup] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)   # 기초지수를 모르는 종목 이름

    @property
    def has_overlap(self) -> bool:
        return bool(self.groups)


def index_of(market: str, ticker: str) -> str | None:
    return INDEX_OF.get((market, (ticker or "").strip().upper()))


def _label(security) -> str:
    if security.market == MARKET_KR:
        return security.display_name or security.ticker
    return security.ticker or security.display_name


def check(portfolio) -> OverlapReport:
    """같은 지수를 여러 번 담았는지 봅니다. 담은 비중이 0 인 종목은 빼고 봅니다."""
    buckets: dict[str, OverlapGroup] = {}
    unknown: list[str] = []
    for sec in portfolio.securities:
        weight = float(sec.target_weight) * 100.0
        if weight <= 0:
            continue
        name = _label(sec)
        index_name = index_of(sec.market, sec.ticker)
        if index_name is None:
            unknown.append(name)
            continue
        buckets.setdefault(index_name, OverlapGroup(index_name)).members.append(
            (name, weight))

    groups = [g for g in buckets.values() if len(g.members) >= 2]
    for g in groups:
        g.members.sort(key=lambda m: -m[1])
    groups.sort(key=lambda g: -g.total_pct)
    return OverlapReport(groups=groups, unknown=sorted(unknown))
