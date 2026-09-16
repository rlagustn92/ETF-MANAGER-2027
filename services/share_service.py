"""
services/share_service.py  --  전술을 주소 한 줄로 주고받기 (?p=...)
====================================================================

왜 QR 이 아니라 주소인가
------------------------
처음에는 캡처 이미지에 QR 을 박으려고 했습니다. "네이버 댓글에는 이미지만 올라간다"고
생각했기 때문인데, **그 전제가 틀렸습니다.** 댓글에는 글자도 올라가고, 우리는 이미
📋 텍스트 버튼으로 댓글용 글을 복사하고 있습니다. 거기에 주소 한 줄을 넣으면 끝입니다.

QR 은 PC 에서 아무도 안 찍습니다. 폰을 꺼내 카메라를 열어야 하고, 크롬에서 QR 을
눌러도 바로 열리지 않습니다. 반면 주소는 눌러서 열거나, 안 되면 복사해서 붙이면 됩니다.

주소에 무엇을 담는가
--------------------
    ?p=US.SCHD:30,KR.458730:20,US.O:15

**종목과 비중만** 담습니다. 전술명·시드·전술판 배치는 안 담습니다.

  - 시드는 받는 사람 것이 따로 있습니다. 남의 시드로 열어주면 곧바로 지워야 합니다.
  - 배치는 전술판이 알아서 합니다.
  - 그리고 주소가 짧아야 댓글이 안 지저분해지고 잘리지도 않습니다.
    (5종목이면 60자 남짓, 10종목이라도 120자 정도)

⚠ 주소는 **완전한 외부 입력**입니다
-----------------------------------
누구든 손으로 고쳐서 보낼 수 있습니다. 여기 있는 decode 는 어떤 쓰레기가 와도
예외를 던지지 않고, 못 읽은 항목은 조용히 버립니다. 주소 하나로 남의 화면을
죽일 수 있으면 안 됩니다.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

import config
import pitch_grid
from models.security import MARKET_KR, MARKET_US, Security
from models.portfolio import Portfolio

QUERY_KEY = "p"

# 주소에서 받아들일 최대 길이. 이보다 길면 애초에 우리가 만든 게 아닙니다.
# (26종목 * 대략 15자 = 400자 정도가 현실적인 최대)
MAX_QUERY_LENGTH = 2_000

# 전술판 슬롯 수보다 많이 받아봐야 자리가 없습니다.
MAX_ITEMS = len(pitch_grid.all_slots())

# 종목코드에 허용할 글자. 미국은 BRK.B 처럼 점이 들어가고, 한국은 0219E0 처럼
# 영문이 섞인 6자리가 있습니다.
_TICKER_OK = re.compile(r"^[A-Za-z0-9.\-]{1,12}$")

_MARKETS = {MARKET_US, MARKET_KR}


@dataclass(frozen=True)
class ShareItem:
    market: str
    ticker: str
    weight_pct: float     # 0~100


# ---------------------------------------------------------------------
# 만들기
# ---------------------------------------------------------------------
def _fmt_weight(weight_ratio: float) -> str:
    """비중을 주소에 넣을 글자로. 30.0 -> "30", 12.5 -> "12.5" (군더더기 0 제거)."""
    try:
        value = round(float(weight_ratio) * 100.0, 2)
    except (TypeError, ValueError):
        return "0"
    if not math.isfinite(value):
        return "0"
    value = max(0.0, min(100.0, value))
    if value == int(value):
        return str(int(value))
    return f"{value:g}"


def encode(portfolio: Portfolio) -> str:
    """전술 -> 주소에 붙일 글자. 담은 게 없으면 빈 문자열."""
    parts: list[str] = []
    for sec in portfolio.securities[:MAX_ITEMS]:
        ticker = (sec.ticker or "").strip()
        if not ticker or sec.market not in _MARKETS:
            continue
        parts.append(f"{sec.market}.{ticker}:{_fmt_weight(sec.target_weight)}")
    return ",".join(parts)


def share_url(portfolio: Portfolio) -> str:
    """댓글에 붙일 주소 한 줄. 담은 게 없으면 앱 주소만."""
    encoded = encode(portfolio)
    if not encoded:
        return config.APP_PUBLIC_URL
    return f"{config.APP_PUBLIC_URL}/?{QUERY_KEY}={encoded}"


# ---------------------------------------------------------------------
# 읽기 (외부 입력 -- 절대 예외를 던지지 않습니다)
# ---------------------------------------------------------------------
def decode(text: str | None) -> list[ShareItem]:
    """주소의 p= 값을 종목 목록으로. 못 읽은 항목은 조용히 버립니다."""
    if not text or not isinstance(text, str):
        return []
    if len(text) > MAX_QUERY_LENGTH:
        return []

    items: list[ShareItem] = []
    seen: set[tuple[str, str]] = set()
    for chunk in text.split(","):
        chunk = chunk.strip()
        if not chunk or ":" not in chunk or "." not in chunk:
            continue
        head, _, weight_text = chunk.rpartition(":")
        # 시장과 종목코드는 **첫 점**에서만 나눕니다. BRK.B 처럼 종목코드 안에도
        # 점이 들어가기 때문입니다.
        market, _, ticker = head.partition(".")
        market = market.strip().upper()
        ticker = ticker.strip().upper()
        if market not in _MARKETS or not _TICKER_OK.match(ticker):
            continue
        try:
            weight = float(weight_text)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(weight) or weight < 0:
            continue
        key = (market, ticker)
        if key in seen:
            continue
        seen.add(key)
        items.append(ShareItem(market=market, ticker=ticker,
                               weight_pct=min(100.0, weight)))
        if len(items) >= MAX_ITEMS:
            break
    return items


def _resolve_name(item: ShareItem) -> tuple[str, str, str]:
    """(정식명, 표시명, 통화). 이름을 못 찾아도 **불러오기는 성공해야 합니다.**

    주소에는 종목코드만 담기므로 이름은 여기서 찾아 붙입니다. 안 붙이면 한국 종목이
    전술판에 "458730" 으로 떠서 뭘 받은 건지 알 수 없습니다.
    검색 목록을 못 가져오는 상황(네트워크 문제 등)에서도 종목코드로라도 열려야 합니다.
    """
    default_currency = "KRW" if item.market == MARKET_KR else "USD"
    try:
        from data.providers import search_provider

        if item.market == MARKET_US:
            hit = search_provider.resolve_us_ticker(item.ticker)
        else:
            hit = next((h for h in search_provider.search(item.ticker, MARKET_KR, limit=20)
                        if h.ticker == item.ticker), None)
    except Exception:
        hit = None
    if hit is None:
        return item.ticker, item.ticker, default_currency
    return hit.name, hit.display_name, hit.currency or default_currency


def to_portfolio(items: list[ShareItem], *, name: str,
                 initial_capital_krw: float) -> Portfolio:
    """받은 종목들로 전술을 만듭니다. 시드와 이름은 **받는 사람 것**을 씁니다."""
    # ⚠ 한도를 받은 개수에 맞춰 올려둬야 합니다. 기본 한도는 축구 한 팀(11명)인데,
    #   보낸 사람은 '종목 더 담기' 를 켜서 26개까지 담을 수 있습니다. 한도를 안 올리면
    #   12번째부터 **조용히 사라집니다** -- 받은 사람은 뭘 못 받았는지도 모릅니다.
    portfolio = Portfolio(
        name=name, initial_capital_krw=initial_capital_krw,
        max_squad_size=max(config.SQUAD_SIZE_DEFAULT, min(len(items), MAX_ITEMS)),
    )
    for item in items:
        full_name, display_name, currency = _resolve_name(item)
        try:
            portfolio.add(Security(
                market=item.market, ticker=item.ticker,
                name=full_name, display_name=display_name, currency=currency,
                asset_type="ETF",
                target_weight=item.weight_pct / 100.0,
            ))
        except ValueError:
            # 중복이거나 슬롯이 다 찼으면 그 종목만 건너뜁니다.
            continue
    return portfolio


def summary(items: list[ShareItem]) -> str:
    """배너에 한 줄로 보여줄 요약. 무엇을 받게 되는지 미리 알려줍니다."""
    if not items:
        return ""
    total = sum(i.weight_pct for i in items)
    return f"{len(items)}종목 · 합계 {total:.0f}%"
