"""
services/naver_link_service.py  --  네이버 증권 종목 페이지 바로가기 주소

무엇을 하나
-----------
종목 상세 패널의 "네이버 ↗" 링크가 열 주소를 만듭니다. 입구는 `naver_url()` 하나입니다.

    naver_url("KR", "458730") -> "https://m.stock.naver.com/domestic/stock/458730/total"
    naver_url("US", "SCHD")   -> "https://m.stock.naver.com/worldstock/etf/SCHD.K"
    naver_url("US", "없는것")  -> None      ← 링크를 안 그립니다

한국과 미국이 왜 다른가
-----------------------
**한국은 코드로 조립됩니다.** 실제로 조립한 주소와 네이버가 알려준 주소가 같은지
069500 / 458730 / 329200 / 0219E0 네 건으로 확인했고 전부 일치했습니다. 그래서 한국은
네트워크를 전혀 쓰지 않습니다.

**미국은 조립할 수 없습니다.** 티커 뒤 거래소 표시가 종목마다 다릅니다.

    SCHD -> /worldstock/etf/SCHD.K      VOO -> /worldstock/etf/VOO   (아무것도 안 붙음)
    TQQQ -> /worldstock/etf/TQQQ.O      O   -> /worldstock/stock/O/total  (ETF 가 아님)

SCHD 와 VOO 는 네이버 기준 **같은 거래소인데 한쪽만 `.K` 가 붙습니다.** 규칙이 없어서
추측하면 빈 페이지로 보내게 됩니다. 그래서 미국은 이 순서로 찾습니다.

    1) data/naver_us_links.py 의 표  (자주 쓰는 종목. 네트워크 0회)
    2) 표에 없으면 네이버 자동완성에 한 번 물어보고 캐시 (24시간)
    3) 그래도 없으면 None -> 링크를 안 그립니다

못 찾으면 안 그린다
-------------------
공식 문서가 있는 API 가 아니라 언제든 바뀔 수 있습니다. 실패했을 때 그럴듯한 주소를
지어내면 사용자를 **빈 페이지로** 보내게 됩니다. 그것보다 링크가 없는 편이 낫습니다.
(프로젝트 절대 규칙: 데이터가 없으면 없다고 한다)
"""

from __future__ import annotations

import re

import requests

import config
from data.naver_us_links import NAVER_US_LINKS
from data.providers import cache
from models.security import MARKET_KR

BASE_URL = "https://m.stock.naver.com"
AC_URL = "https://ac.stock.naver.com/ac"

# 남의 서버를 두드리면서 신원을 안 밝히는 것은 예의가 아닙니다. 지금은 헤더가 없어도
# 응답하지만 저쪽이 언제든 요구하도록 바꿀 수 있습니다.
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://m.stock.naver.com/"}


def normalize_ticker(ticker: str) -> str:
    """비교·질의용으로 영문/숫자만 남깁니다.

    버크셔 B주가 실제로 이 처리를 필요로 했습니다. 우리 티커는 `BRK-B` 인데 네이버는
    코드를 `BRK B`(공백) 로 들고 있습니다. `BRK-B` 로도 `BRK.B` 로도 검색 결과가
    **아예 안 나오고** `BRKB` 로 해야 나옵니다.
    """
    return re.sub(r"[^A-Za-z0-9]", "", str(ticker or "")).upper()


def korean_url(ticker: str) -> str:
    """한국 종목 주소. 코드만 있으면 만들 수 있습니다(네트워크 없음).

    코드에 영문이 섞인 ETN(예: 0219E0)도 같은 형식으로 동작하는 것을 확인했습니다.
    """
    return f"{BASE_URL}/domestic/stock/{str(ticker).strip()}/total"


def _lookup_us(ticker: str) -> str | None:
    """네이버 자동완성에 물어 미국 종목 주소를 얻습니다. 못 찾거나 실패하면 None."""
    want = normalize_ticker(ticker)
    if not want:
        return None
    try:
        resp = requests.get(AC_URL, params={"q": want, "target": "stock"},
                            headers=HEADERS, timeout=config.NAVER_TIMEOUT_SECONDS)
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    try:
        data = resp.json()
    except ValueError:
        return None
    for item in data.get("items") or []:
        # 이름이 비슷한 다른 나라 종목이 같이 옵니다. 코드 완전일치 + 국가로 걸러야
        # "SCHD" 를 물었는데 엉뚱한 나라 종목이 잡히는 일이 없습니다.
        if (normalize_ticker(item.get("code", "")) == want
                and item.get("nationCode") == "USA"
                and item.get("url")):
            # ⚠ 돌려받은 url 을 그대로 씁니다. ETF 는 /worldstock/etf/...(끝에 /total 없음),
            #   일반 주식은 /worldstock/stock/.../total 이라 조립하면 틀립니다.
            return BASE_URL + str(item["url"])
    return None


def us_url(ticker: str) -> str | None:
    """미국 종목 주소. 표에 있으면 바로, 없으면 한 번 물어보고 캐시합니다."""
    key = normalize_ticker(ticker)
    if not key:
        return None
    hit = NAVER_US_LINKS.get(key)
    if hit:
        return hit
    # 표에 없는 종목(사용자가 직접 검색해 담은 티커). 결과는 24시간 캐시되고
    # 모든 접속자가 공유하므로 같은 종목을 다시 물어보지 않습니다.
    #
    # 못 찾은 결과(None)도 캐시됩니다. 일시적인 장애로 링크가 한동안 안 보일 수는
    # 있지만, 화면을 다시 그릴 때마다 네이버를 두드리는 것보다 낫습니다.
    # 관리자는 '데이터 업데이트' 버튼(cache.invalidate)으로 즉시 지울 수 있습니다.
    return cache.get_or_set(f"naver:url:{key}", config.CACHE_TTL_NAVER_LINK_SECONDS,
                            lambda: _lookup_us(key))


def naver_url(market: str, ticker: str) -> str | None:
    """네이버 증권에서 이 종목을 여는 주소. 확인할 수 없으면 None.

    PC 와 모바일이 같은 주소로 열립니다(m.stock.naver.com 은 원래 모바일용 화면이고
    PC 에서도 그대로 열립니다). 앱으로 넘기는 커스텀 스킴은 쓰지 않습니다 — 공개 규격이
    아니라 저쪽이 바꾸면 조용히 깨지고, 앱이 없는 사용자는 빈 탭만 보게 됩니다.
    """
    if not str(ticker or "").strip():
        return None
    if (market or "").upper() == MARKET_KR:
        return korean_url(ticker)
    return us_url(ticker)
