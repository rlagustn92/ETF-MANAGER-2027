"""
presets.py  --  "예시로 시작하기" 샘플 포트폴리오 3종
=====================================================

처음 앱을 연 사람이 빈 화면 앞에서 막막하지 않도록, 버튼 한 번으로 채워지는
예시 구성을 제공합니다 (사용자 요청).

중요 -- 이것은 "추천 종목"이 아닙니다
------------------------------------
이 앱은 투자 판단/추천을 제공하지 않습니다(인수인계서 원칙). 아래 구성은
"이런 식으로 칸을 채워서 써보세요" 를 보여주는 **예시**이며, 좋은 조합이라는
평가나 점수가 아닙니다. 그래서 세 가지를 "수익률이 높은 순"이 아니라
**분배금이 나오는 방식**으로 나눴습니다. 이건 주관적 평가가 아니라 사실 구분입니다.

  - 안정형 : 전통 배당주·리츠·국채 중심 (분배금의 출처가 배당/임대료/이자)
  - 보통형 : 전통 배당 + 커버드콜 절반씩
  - 공격형 : 커버드콜 중심 (옵션 프리미엄으로 분배금을 만들어 분배율이 높은 대신
             가격 변동과 원금 손실 위험이 큽니다)

종목·명칭의 출처
----------------
아래 티커/명칭은 임의로 적은 것이 아니라, 이 앱이 실제로 쓰는 데이터 소스
(yfinance / FinanceDataReader 검색 인덱스)에서 조회해 확인한 값입니다.
가격과 분배금도 전부 실시간 조회되므로, 화면에 뜨는 숫자는 예시가 아니라 실제 값입니다.
종목을 바꾸거나 추가할 때도 반드시 실제 조회가 되는지 확인하고 넣으세요
(tests/test_presets.py 가 비중 합계 100% 와 중복 여부를 지켜줍니다).
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

from models.portfolio import Portfolio
from models.security import Security

# 예시는 항상 시드 1억 기준으로 채웁니다 (사용자 요청).
PRESET_CAPITAL_KRW: int = 100_000_000


@dataclass(frozen=True)
class PresetItem:
    market: str
    ticker: str
    name: str
    currency: str
    weight_pct: float
    asset_type: str = "ETF"
    display_name: str = ""

    def shown_name(self) -> str:
        return self.display_name or (self.name if self.market == "KR" else self.ticker)


@dataclass(frozen=True)
class Preset:
    key: str
    label: str
    summary: str          # 버튼 아래 한 줄 설명
    items: tuple[PresetItem, ...]
    # 이 예시를 불러올 때 채울 시드. 없으면 기본값(1억).
    # "월 ○○만원 받기" 예시는 원금이 곧 주제라서 예시마다 다릅니다.
    capital_krw: int = PRESET_CAPITAL_KRW

    def total_weight_pct(self) -> float:
        return sum(i.weight_pct for i in self.items)


STABLE = Preset(
    key="stable",
    label="안정배당형",
    summary="전통 배당주·리츠·국채 중심. 분배금이 배당/임대료/이자에서 나옵니다.",
    items=(
        PresetItem("US", "SCHD", "Schwab US Dividend Equity ETF", "USD", 30.0),
        PresetItem("KR", "458730", "TIGER 미국배당다우존스", "KRW", 20.0),
        PresetItem("KR", "329200", "TIGER 리츠부동산인프라", "KRW", 20.0),
        PresetItem("US", "O", "Realty Income Corporation", "USD", 15.0, asset_type="STOCK"),
        PresetItem("US", "TLT", "iShares 20+ Year Treasury Bond ETF", "USD", 15.0),
    ),
)

BALANCED = Preset(
    key="balanced",
    label="보통배당형",
    summary="전통 배당과 커버드콜을 반반 섞은 구성입니다.",
    items=(
        PresetItem("US", "SCHD", "Schwab US Dividend Equity ETF", "USD", 25.0),
        PresetItem("US", "JEPI", "JPMorgan Equity Premium Income ETF", "USD", 20.0),
        PresetItem("US", "VYM", "Vanguard High Dividend Yield ETF", "USD", 15.0),
        PresetItem("KR", "161510", "PLUS 고배당주", "KRW", 15.0),
        PresetItem("KR", "329200", "TIGER 리츠부동산인프라", "KRW", 15.0),
        PresetItem("KR", "0219E0", "KODEX 200커버드콜액티브", "KRW", 10.0),
    ),
)

AGGRESSIVE = Preset(
    key="aggressive",
    label="공격배당형",
    summary="커버드콜 중심. 분배율이 높은 대신 가격 변동·원금 손실 위험이 큽니다.",
    items=(
        PresetItem("US", "JEPQ", "JPMorgan Nasdaq Equity Premium Income ETF", "USD", 30.0),
        PresetItem("US", "QYLD", "Global X NASDAQ 100 Covered Call ETF", "USD", 20.0),
        PresetItem("KR", "441680", "TIGER 미국나스닥100커버드콜(합성)", "KRW", 20.0),
        PresetItem("KR", "0177R0", "TIGER 반도체TOP10커버드콜액티브", "KRW", 15.0),
        PresetItem("KR", "0219E0", "KODEX 200커버드콜액티브", "KRW", 15.0),
    ),
)


# =====================================================================
# "월 ○○만원 받기" 예시 2종
# =====================================================================
# 한국에서 배당 투자의 목표는 대부분 "월 얼마"로 잡힙니다(사용자 요청).
# 위의 3종이 **성향**으로 나눈 것이라면, 아래 2종은 **목표 금액**으로 나눈 것입니다.
#
# ⚠️ 왜 "5천만원으로 월 100만원" 이 없는가 -- 만들 수 있는데 안 만든 게 아니라,
#    정직하게 만들 수가 없습니다.
#      월 100만원 / 5천만원 = 연 1,200만원 = **분배율 24%**
#    실제로 조회해 보면(2026-09 기준) 실적이 검증된 국내외 상품 중 최고가 22.17%
#    (TIGER 배당커버드콜액티브)입니다. 한 종목에 5천만원을 전부 넣어도 월 92만원이고,
#    그마저 단일 종목 집중입니다. 24%를 넘기려면
#      - YieldMax 계열(YMAX 65%) 처럼 원금을 깎아 분배금을 만드는 상품이거나
#      - 상장 2~5개월짜리 실적을 연환산한 **추정치** 종목
#    을 넣어야 합니다. 앱이 그런 구성을 "예시"로 내놓으면 처음 시작하는 사람에게
#    24% 를 쫓으라고 가르치는 셈이라 넣지 않았습니다.
#    대신 같은 분배율(12%)에서 원금만 절반인 "월 50만원" 예시를 둡니다.
#    원금이 절반이면 분배금도 절반이라는 것 자체가 보여줄 가치가 있습니다.
#
# 아래 분배율은 전부 **실적(최근 12개월 실제 지급액)** 이 있는 종목만 골랐습니다.
# 상장한 지 얼마 안 돼 연환산 추정치가 뜨는 종목은 의도적으로 제외했습니다.

# 종목 고른 기준 (사용자 요청): 대중적이고 거래량이 많은 것, 그리고 **큰 지수를
# 따라가는 것**. 나스닥100 / 코스피200 / 미국배당다우존스 / 국내 리츠처럼 기초자산이
# 넓은 상품만 썼습니다. 러셀2000(소형주)이나 단일 테마는 뺐습니다.
#
# 미국과 한국을 **반씩** 섞었습니다. 한쪽에 몰면 환율이 움직일 때 통째로 흔들립니다.
# 한 종목이 20%를 넘지 않게 했습니다.
#
# ⚠️ 여기서 알아둘 상충 관계: **변동성이 낮을수록 분배율도 낮습니다.**
#    실측해 보면 저변동 상품(JEPI·XYLD·SPYI 중심)만으로 짜면 10.75%(월 89만원)까지가
#    한계였습니다. 월 100만원(12%)을 맞추려면 커버드콜 비중이 높아질 수밖에 없고,
#    그만큼 가격이 오를 때 덜 먹습니다. 목표 금액이 공짜가 아니라는 뜻입니다.
#
#    그래서 분배율이 높은 두 종목(TIGER 배당커버드콜액티브 22.17%,
#    KODEX 200타겟위클리커버드콜 15.87%)을 각각 10% 씩만 넣었습니다. 이 둘 덕분에
#    목표를 넘기지만, 분배율이 높다는 건 그만큼 공격적이라는 뜻이라 비중을 낮게
#    잡았습니다. 둘 다 실적(최근 12개월 실제 지급액) 기준이며 추정치가 아닙니다.

INCOME_100_1E = Preset(
    key="income100_1e",
    label="월 100만원 · 1억",
    summary=("시드 1억으로 월 100만원을 목표로 한 예시(분배율 약 12%). "
             "미국·한국을 반씩 섞고 큰 지수를 따라가는 상품만 담았습니다."),
    capital_krw=100_000_000,
    items=(
        # 미국 50%
        PresetItem("US", "JEPQ", "JPMorgan Nasdaq Equity Premium Income ETF", "USD", 15.0),
        PresetItem("US", "QQQI", "NEOS Nasdaq-100 High Income ETF", "USD", 15.0),
        PresetItem("US", "QYLD", "Global X NASDAQ 100 Covered Call ETF", "USD", 10.0),
        # 분배율은 낮지만(약 3%) 커버드콜만으로 쏠리는 걸 눌러 주는 자리입니다.
        PresetItem("US", "SCHD", "Schwab US Dividend Equity ETF", "USD", 10.0),
        # 한국 50%
        PresetItem("KR", "441680", "TIGER 미국나스닥100커버드콜(합성)", "KRW", 15.0),
        PresetItem("KR", "472150", "TIGER 배당커버드콜액티브", "KRW", 10.0),
        PresetItem("KR", "498400", "KODEX 200타겟위클리커버드콜", "KRW", 10.0),
        PresetItem("KR", "458760", "TIGER 미국배당다우존스타겟커버드콜2호", "KRW", 10.0),
        PresetItem("KR", "329200", "TIGER 리츠부동산인프라", "KRW", 5.0),
    ),
)

INCOME_50_5000 = Preset(
    key="income50_5000",
    label="월 50만원 · 5천만원",
    summary=("시드 5천만원으로 월 50만원을 목표로 한 예시(분배율 약 12%). "
             "위와 같은 방식이되 원금이 절반이라 종목 수를 줄였습니다."),
    capital_krw=50_000_000,
    items=(
        # 미국 50%
        PresetItem("US", "JEPQ", "JPMorgan Nasdaq Equity Premium Income ETF", "USD", 20.0),
        PresetItem("US", "QQQI", "NEOS Nasdaq-100 High Income ETF", "USD", 15.0),
        PresetItem("US", "SCHD", "Schwab US Dividend Equity ETF", "USD", 15.0),
        # 한국 50%
        PresetItem("KR", "441680", "TIGER 미국나스닥100커버드콜(합성)", "KRW", 20.0),
        PresetItem("KR", "472150", "TIGER 배당커버드콜액티브", "KRW", 10.0),
        PresetItem("KR", "498400", "KODEX 200타겟위클리커버드콜", "KRW", 10.0),
        PresetItem("KR", "458760", "TIGER 미국배당다우존스타겟커버드콜2호", "KRW", 10.0),
    ),
)

PRESETS: tuple[Preset, ...] = (STABLE, BALANCED, AGGRESSIVE,
                               INCOME_100_1E, INCOME_50_5000)

# 예시 버튼 옆의 "초기화". 종목이 하나도 없는 빈 전술로 되돌립니다 (사용자 요청).
# 예시 3종과 같은 확인 절차를 타도록 Preset 모양을 그대로 씁니다.
RESET = Preset(
    key="reset",
    label="초기화",
    summary="담은 종목을 모두 비우고 처음 상태로 되돌립니다.",
    items=(),
)

ALL_BUTTONS: tuple[Preset, ...] = PRESETS + (RESET,)


def get(key: str) -> Preset | None:
    return next((p for p in ALL_BUTTONS if p.key == key), None)


def build_portfolio(preset: Preset) -> Portfolio:
    """예시 구성대로 채워진 새 Portfolio 를 만듭니다 (슬롯 배치는 Portfolio.add 가 담당).

    items 가 비어 있으면(초기화) 종목 없는 빈 전술이 됩니다.
    """
    p = Portfolio(name=f"{preset.label} 예시" if preset.items else "",
                  initial_capital_krw=preset.capital_krw)
    for item in preset.items:
        p.add(Security(
            market=item.market, ticker=item.ticker, name=item.name,
            display_name=item.shown_name(), currency=item.currency,
            asset_type=item.asset_type, target_weight=item.weight_pct / 100.0,
        ))
    return p


def yahoo_finance_url(market: str, ticker: str) -> str:
    """야후 파이낸스에서 이 종목을 여는 주소 (사용자 요청: 티커만 보고는 뭔지 모를 때).

    미국 종목은 티커가 그대로 야후 심볼이라 시세 페이지로 바로 보냅니다.
    한국 종목은 야후 심볼이 .KS(코스피)/.KQ(코스닥) 중 무엇인지 티커만으로는 확정할 수
    없어서(우리 provider 도 두 개를 번갈아 시도합니다), 잘못된 페이지로 보내는 대신
    검색 결과로 보냅니다.
    """
    t = quote(str(ticker).strip(), safe="")
    if (market or "").upper() == "KR":
        return f"https://finance.yahoo.com/lookup/?s={t}"
    return f"https://finance.yahoo.com/quote/{t}/"


def toss_invest_url(market: str, ticker: str) -> str:
    """토스증권에서 이 종목을 여는 주소.

    한국 종목은 야후에서 잘 안 나와서 토스증권 쪽이 훨씬 쓸모 있습니다(사용자 요청).
    주소 형식은 실제 사이트에서 확인했습니다:
      - 한국: /stocks/A + 종목코드  (예: A329200, 영문 섞인 A0219E0 도 동작)
      - 미국: /stocks/ + 티커       (예: SCHD -> 내부 ID 로 자동 이동)
    """
    raw = str(ticker).strip()
    code = f"A{raw}" if (market or "").upper() == "KR" else raw
    return f"https://www.tossinvest.com/stocks/{quote(code, safe='')}"
