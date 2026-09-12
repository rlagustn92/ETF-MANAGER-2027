"""
data/providers/alpaca_provider.py  --  미국 주식/ETF 데이터 (Alpaca Market Data API)

왜 있나
-------
yfinance 는 공식 API 가 아니라 **서버 IP 기준**으로 차단될 수 있습니다. 내 PC 에서 혼자
쓸 때는 괜찮지만, 배포해서 여러 명이 동시에 들어오면 한 IP 에서 요청이 몰려 막힐 수 있어요.
Alpaca 는 **API 키 기준 할당량**이라 그 문제가 없습니다.

한계: **미국 종목만 있습니다.** 한국 종목(329200 등)은 "invalid symbol" 로 거절됩니다.
따라서 US 만 이쪽으로 보내고, 한국은 계속 FinanceDataReader + yfinance 를 씁니다.

실행 검증 (2026-09, 무료 계정으로 실제 응답 확인)
------------------------------------------------
- GET /v2/stocks/{sym}/trades/latest?feed=iex      -> {"trade": {"p": 34.13, "t": "..."}}
- GET /v2/stocks/{sym}/bars?adjustment=split       -> 분할만 소급 반영 (배당 조정 안 함)
      NVDA 2024-06-03 종가: raw 1149.99 / split 115.00 / all 114.67
      => 이 앱은 "가격은 분할 소급, 배당은 별도" 전제이므로 **반드시 adjustment=split**.
         'all' 을 쓰면 배당이 가격에도 반영되어 분배금이 이중 계산됩니다.
- GET /v1/corporate-actions?types=cash_dividend    -> {"cash_dividends": [{"ex_date","rate",...}]}
      무료 티어에서도 나옵니다. SCHD 분기 4건 / JEPQ 월 13건 확인.
- GET /v1/corporate-actions?types=forward_split    -> {"forward_splits": [{"ex_date","new_rate","old_rate"}]}
      NVDA 2024-06-10 new_rate=10, old_rate=1 (= 10:1). 비율은 new/old.
- 5년치 일봉(1429건)이 limit=10000 이면 한 페이지에 옵니다(안전하게 페이징도 구현).

무료 티어는 IEX 체결 기준이라 통합시세(SIP)와 소수점 단위 차이가 날 수 있습니다.
포트폴리오 구성 용도에는 충분하지만, 정확한 종가가 필요하면 유료 플랜이 필요합니다.

키 설정
-------
`.streamlit/secrets.toml` (또는 환경변수):
    ALPACA_API_KEY = "..."
    ALPACA_SECRET_KEY = "..."
키가 없으면 이 provider 는 사용되지 않고 기존 yfinance 로 동작합니다 (registry.py 참고).
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta

import pandas as pd
import requests

import config
from data.providers import cache
from data.providers.base import (
    DataUnavailable,
    HISTORY_CLOSE_COL,
    MarketDataProvider,
    PriceQuote,
)

DATA_BASE = "https://data.alpaca.markets"
FEED = "iex"          # 무료 티어
TIMEOUT = 30


def credentials() -> tuple[str, str] | None:
    """(key, secret) 또는 키가 없으면 None.

    Streamlit secrets 를 먼저 보고, 없으면 환경변수를 봅니다.
    (provider 가 Streamlit 에 강하게 묶이지 않도록 import 는 함수 안에서)
    """
    key = secret = ""
    try:
        import streamlit as st
        key = str(st.secrets.get("ALPACA_API_KEY", "") or "")
        secret = str(st.secrets.get("ALPACA_SECRET_KEY", "") or "")
    except Exception:
        pass
    if not (key and secret):
        key = os.environ.get("ALPACA_API_KEY", "")
        secret = os.environ.get("ALPACA_SECRET_KEY", "")
    return (key, secret) if (key and secret) else None


def is_configured() -> bool:
    return credentials() is not None


def _headers() -> dict:
    creds = credentials()
    if creds is None:
        raise DataUnavailable("Alpaca API 키가 설정되어 있지 않습니다.")
    return {"APCA-API-KEY-ID": creds[0], "APCA-API-SECRET-KEY": creds[1]}


def _get(path: str, params: dict) -> dict:
    try:
        r = requests.get(f"{DATA_BASE}{path}", headers=_headers(), params=params,
                         timeout=TIMEOUT)
    except requests.RequestException as e:
        raise DataUnavailable(f"Alpaca 요청 실패: {e}") from e
    if r.status_code == 400:
        # 한국 종목 등 Alpaca 에 없는 심볼
        raise DataUnavailable(f"Alpaca 에 없는 종목입니다: {params.get('symbols') or path}")
    if r.status_code in (401, 403):
        raise DataUnavailable("Alpaca 인증 실패 — API 키를 확인하세요.")
    if r.status_code == 429:
        raise DataUnavailable("Alpaca 요청 한도를 초과했습니다. 잠시 후 다시 시도하세요.")
    if r.status_code != 200:
        raise DataUnavailable(f"Alpaca 오류 (HTTP {r.status_code})")
    try:
        return r.json()
    except ValueError as e:
        raise DataUnavailable(f"Alpaca 응답을 해석하지 못했습니다: {e}") from e


def _to_day(ts: str) -> pd.Timestamp:
    """'2025-08-08T04:00:00Z' / '2025-09-24' -> 날짜만 남긴 Timestamp."""
    return pd.Timestamp(datetime.fromisoformat(ts.replace("Z", "+00:00")).date()) \
        if "T" in ts else pd.Timestamp(ts)


class AlpacaDataProvider(MarketDataProvider):
    name = "alpaca"

    # ---------------------------------------------------------------
    def get_price_history(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        key = f"alpaca:hist:{ticker}:{start}:{end}"

        def _load() -> pd.DataFrame:
            rows: list[dict] = []
            page_token = None
            for _ in range(20):        # 안전장치: 무한 페이징 방지
                params = {
                    "timeframe": "1Day",
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    # 분할만 소급 반영. 배당은 get_distributions 로 따로 받습니다.
                    "adjustment": "split",
                    "feed": FEED,
                    "limit": 10000,
                }
                if page_token:
                    params["page_token"] = page_token
                j = _get(f"/v2/stocks/{ticker}/bars", params)
                rows.extend(j.get("bars") or [])
                page_token = j.get("next_page_token")
                if not page_token:
                    break
            if not rows:
                raise DataUnavailable(
                    f"[{ticker}] {start}~{end} 구간의 미국 가격 데이터를 가져오지 못했습니다(Alpaca)."
                )
            idx = pd.DatetimeIndex([_to_day(b["t"]) for b in rows], name="date")
            df = pd.DataFrame({HISTORY_CLOSE_COL: [float(b["c"]) for b in rows]}, index=idx)
            df = df[~df.index.duplicated(keep="last")].sort_index()
            df.attrs["currency"] = "USD"
            df.attrs["source"] = self.name
            return df

        return cache.get_or_set(key, config.CACHE_TTL_PRICE_SECONDS, _load)

    # ---------------------------------------------------------------
    def get_latest_price(self, ticker: str) -> PriceQuote:
        key = f"alpaca:last:{ticker}"

        def _load() -> PriceQuote:
            j = _get(f"/v2/stocks/{ticker}/trades/latest", {"feed": FEED})
            trade = j.get("trade") or {}
            price = trade.get("p")
            if price is None:
                raise DataUnavailable(f"[{ticker}] Alpaca 최신가가 비어 있습니다.")
            as_of = _to_day(trade.get("t") or date.today().isoformat()).date()
            return PriceQuote(ticker=ticker, price=float(price), currency="USD",
                              as_of=as_of, source=self.name)

        return cache.get_or_set(key, config.CACHE_TTL_LATEST_PRICE_SECONDS, _load)

    # ---------------------------------------------------------------
    def _corporate_actions(self, ticker: str, kind: str, start: date, end: date) -> list[dict]:
        """kind: 'cash_dividend' | 'forward_split' | 'reverse_split'"""
        out: list[dict] = []
        page_token = None
        for _ in range(20):
            params = {"symbols": ticker, "types": kind,
                      "start": start.isoformat(), "end": end.isoformat(), "limit": 1000}
            if page_token:
                params["page_token"] = page_token
            j = _get("/v1/corporate-actions", params)
            ca = j.get("corporate_actions") or {}
            for items in ca.values():          # 'cash_dividends', 'forward_splits' 등
                out.extend(items or [])
            page_token = j.get("next_page_token")
            if not page_token:
                break
        return out

    def get_distributions(self, ticker: str, start: date, end: date) -> pd.Series:
        # 캐시는 넉넉한 구간으로 한 번만 받아두고, 요청 구간은 잘라서 돌려줍니다.
        #
        # ⚠ 중요: Alpaca 의 start/end 는 배당락일(ex_date)이 아니라 **처리일(process_date)**
        # 기준으로 거릅니다. 예) O 의 ex_date 2026-08-31 배당은 process_date 가 2026-09-15 라,
        # end=오늘(9/12) 로 조회하면 빠집니다. 우리는 ex_date 로 색인하므로, 그대로 두면
        # **월배당 종목의 가장 최근 1건이 매번 누락**되어 분배금이 낮게 계산됩니다.
        # 그래서 조회 구간을 미래로 넉넉히 늘려 받고, ex_date 기준 자르기는 아래에서 직접 합니다.
        wide_start = min(start, date.today() - timedelta(days=365 * 6))
        wide_end = max(end, date.today()) + timedelta(days=120)
        key = f"alpaca:div:{ticker}:{wide_start}:{wide_end}"

        def _load_all() -> pd.Series:
            items = self._corporate_actions(ticker, "cash_dividend", wide_start, wide_end)
            if not items:
                return pd.Series(dtype="float64",
                                 index=pd.DatetimeIndex([], name="date"), name="distribution")
            # ex_date 기준 (yfinance 의 .dividends 인덱스와 같은 기준)
            pairs = [(_to_day(i["ex_date"]), float(i["rate"]))
                     for i in items if i.get("ex_date") and i.get("rate") is not None]
            if not pairs:
                return pd.Series(dtype="float64",
                                 index=pd.DatetimeIndex([], name="date"), name="distribution")
            pairs.sort(key=lambda p: p[0])
            return pd.Series([v for _, v in pairs],
                             index=pd.DatetimeIndex([d for d, _ in pairs], name="date"),
                             name="distribution")

        alls = cache.get_or_set(key, config.CACHE_TTL_DISTRIBUTION_SECONDS, _load_all)
        if len(alls) == 0:
            return alls
        mask = (alls.index >= pd.Timestamp(start)) & (alls.index <= pd.Timestamp(end))
        return alls.loc[mask]

    # ---------------------------------------------------------------
    def get_splits(self, ticker: str, start: date, end: date) -> pd.Series:
        key = f"alpaca:split:{ticker}:{start}:{end}"

        def _load() -> pd.Series:
            # 배당과 같은 이유로(처리일 기준 필터) 조회 구간을 앞뒤로 넉넉히 잡습니다.
            q_start, q_end = start - timedelta(days=30), end + timedelta(days=120)
            # 정/역분할을 한 번에 요청합니다(요청 수 절반, 중복 위험 없음).
            items = self._corporate_actions(ticker, "forward_split,reverse_split",
                                            q_start, q_end)
            pairs = []
            for i in items:
                old = float(i.get("old_rate") or 0)
                new = float(i.get("new_rate") or 0)
                if old > 0 and new > 0 and i.get("ex_date"):
                    pairs.append((_to_day(i["ex_date"]), new / old))   # 10:1 -> 10.0
            if not pairs:
                return pd.Series(dtype="float64",
                                 index=pd.DatetimeIndex([], name="date"), name="split")
            pairs.sort(key=lambda p: p[0])
            s = pd.Series([v for _, v in pairs],
                          index=pd.DatetimeIndex([d for d, _ in pairs], name="date"),
                          name="split")
            # 넓게 받아왔으니 ex_date 기준으로 요청 구간만 남깁니다.
            mask = (s.index >= pd.Timestamp(start)) & (s.index <= pd.Timestamp(end))
            return s.loc[mask]

        return cache.get_or_set(key, config.CACHE_TTL_PRICE_SECONDS, _load)

    # ---------------------------------------------------------------
    def get_info(self, ticker: str) -> dict:
        return {}
