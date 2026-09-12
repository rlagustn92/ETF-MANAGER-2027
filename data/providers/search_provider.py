"""
data/providers/search_provider.py  --  종목 검색 (인수인계서 18, 19, 58)
=====================================================================

검색 기준: ticker / 종목명 / 한국 종목코드 / 영문명
시장 필터: 전체 / 미국 / 한국

- 한국 목록: FinanceDataReader 의 KRX + ETF/KR 목록 (24h 캐시)
- 미국 목록: us_seed.US_SEED (시드) + 시드에 없으면 yfinance 로 실제 조회하여 확인
"""

from __future__ import annotations

from dataclasses import dataclass

import config
from data.providers import cache
from models.security import MARKET_KR, MARKET_US

from data.providers.us_seed import US_SEED

try:
    import FinanceDataReader as fdr
except Exception:  # pragma: no cover
    fdr = None

try:
    import yfinance as yf
except Exception:  # pragma: no cover
    yf = None


@dataclass
class SearchHit:
    market: str          # "US" | "KR"
    ticker: str
    name: str
    display_name: str
    currency: str
    asset_type: str      # "ETF" | "STOCK" (참고용)
    exchange: str = ""

    def label(self) -> str:
        if self.market == MARKET_KR:
            return f"{self.display_name} ({self.ticker})"
        return f"{self.ticker} — {self.name}"


# ---------------------------------------------------------------------
# 한국 목록
# ---------------------------------------------------------------------
def _load_kr_universe() -> list[SearchHit]:
    if fdr is None:
        return []

    def _load() -> list[SearchHit]:
        hits: list[SearchHit] = []
        seen: set[str] = set()
        # 개별주 + 우선주 등 (KRX)
        try:
            krx = fdr.StockListing("KRX")
            code_col = "Code" if "Code" in krx.columns else krx.columns[0]
            name_col = "Name" if "Name" in krx.columns else krx.columns[2]
            mkt_col = "Market" if "Market" in krx.columns else None
            for _, r in krx.iterrows():
                code = str(r[code_col]).zfill(6)
                if code in seen:
                    continue
                seen.add(code)
                nm = str(r[name_col])
                hits.append(SearchHit(
                    market=MARKET_KR, ticker=code, name=nm, display_name=nm,
                    currency="KRW", asset_type="STOCK",
                    exchange=str(r[mkt_col]) if mkt_col else "",
                ))
        except Exception:
            pass
        # 한국 ETF
        try:
            etf = fdr.StockListing("ETF/KR")
            sym_col = "Symbol" if "Symbol" in etf.columns else etf.columns[0]
            name_col = "Name" if "Name" in etf.columns else etf.columns[2]
            for _, r in etf.iterrows():
                code = str(r[sym_col]).zfill(6)
                nm = str(r[name_col])
                if code in seen:
                    # ETF 로 유형 갱신
                    for h in hits:
                        if h.ticker == code:
                            h.asset_type = "ETF"
                    continue
                seen.add(code)
                hits.append(SearchHit(
                    market=MARKET_KR, ticker=code, name=nm, display_name=nm,
                    currency="KRW", asset_type="ETF", exchange="KRX",
                ))
        except Exception:
            pass
        return hits

    return cache.get_or_set("search:kr:universe", config.CACHE_TTL_SEARCH_SECONDS, _load)


# ---------------------------------------------------------------------
# 미국 목록 (시드)
# ---------------------------------------------------------------------
def _us_seed_hits() -> list[SearchHit]:
    return [
        SearchHit(market=MARKET_US, ticker=t, name=n, display_name=t,
                  currency="USD", asset_type=a, exchange="US")
        for (t, n, a) in US_SEED
    ]


def resolve_us_ticker(ticker: str) -> SearchHit | None:
    """시드에 없는 미국 티커를 yfinance 로 실제 조회하여 확인. 없으면 None."""
    t = ticker.strip().upper()
    if not t:
        return None
    for h in _us_seed_hits():
        if h.ticker.upper() == t:
            return h
    if yf is None:
        return None

    def _load() -> SearchHit | None:
        try:
            tk = yf.Ticker(t)
            fi = tk.fast_info
            last = fi.get("lastPrice") if hasattr(fi, "get") else None
            cur = (fi.get("currency") if hasattr(fi, "get") else None) or "USD"
            qt = (fi.get("quoteType") if hasattr(fi, "get") else None) or ""
        except Exception:
            return None
        if last is None:
            return None
        name = t
        try:
            info = tk.get_info() if hasattr(tk, "get_info") else tk.info
            name = info.get("shortName") or info.get("longName") or t
        except Exception:
            pass
        atype = "ETF" if str(qt).upper() == "ETF" else "STOCK"
        return SearchHit(market=MARKET_US, ticker=t, name=name, display_name=t,
                         currency=str(cur).upper(), asset_type=atype, exchange="US")

    return cache.get_or_set(f"search:us:resolve:{t}", config.CACHE_TTL_SEARCH_SECONDS, _load)


# ---------------------------------------------------------------------
# 통합 검색
# ---------------------------------------------------------------------
def search(query: str, market_filter: str = "ALL", limit: int = 40) -> list[SearchHit]:
    """market_filter: "ALL" | "US" | "KR" (인수인계서 19)."""
    q = (query or "").strip().lower()
    mf = (market_filter or "ALL").upper()

    pool: list[SearchHit] = []
    if mf in ("ALL", MARKET_US):
        pool.extend(_us_seed_hits())
    if mf in ("ALL", MARKET_KR):
        pool.extend(_load_kr_universe())

    if not q:
        # 빈 검색어: 대표 종목 위주로 앞부분만
        return pool[:limit]

    def matches(h: SearchHit) -> int:
        """0 = 미매치, 높을수록 우선순위."""
        tkr = h.ticker.lower()
        nm = h.name.lower()
        dn = h.display_name.lower()
        if q == tkr:
            return 100
        if tkr.startswith(q):
            return 80
        if q in tkr:
            return 60
        if q in nm or q in dn:
            return 40
        return 0

    scored = [(matches(h), h) for h in pool]
    scored = [(s, h) for (s, h) in scored if s > 0]
    scored.sort(key=lambda x: (-x[0], x[1].ticker))
    results = [h for _, h in scored][:limit]

    # 미국 티커 직접 입력 대응: 결과가 없고 영문/숫자 티커처럼 보이면 실시간 확인
    if not results and mf in ("ALL", MARKET_US) and query.strip().replace("-", "").replace(".", "").isalnum():
        hit = resolve_us_ticker(query)
        if hit is not None:
            results = [hit]
    return results
