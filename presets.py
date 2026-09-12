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

PRESETS: tuple[Preset, ...] = (STABLE, BALANCED, AGGRESSIVE)

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
                  initial_capital_krw=PRESET_CAPITAL_KRW)
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
