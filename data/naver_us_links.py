"""
data/naver_us_links.py  --  미국 종목의 네이버 증권 주소 (자동 생성)

**손으로 고치지 마세요.** tools/refresh_naver_links.py 가 만듭니다.

미국은 티커만으로 주소를 조립할 수 없어서(거래소 접미사가 종목마다 다름)
네이버 자동완성에 물어본 결과를 박아둔 표입니다. 여기 있는 종목은 실행 중에
네트워크를 전혀 쓰지 않습니다. 여기 없는 티커만 그때 물어봅니다.

키는 영문/숫자만 남긴 티커입니다(BRK-B -> BRKB).
"""

from __future__ import annotations

NAVER_US_LINKS: dict[str, str] = {
    "AAPL": "https://m.stock.naver.com/worldstock/stock/AAPL.O/total",
    "AMZN": "https://m.stock.naver.com/worldstock/stock/AMZN.O/total",
    "BIL": "https://m.stock.naver.com/worldstock/etf/BIL",
    "BND": "https://m.stock.naver.com/worldstock/etf/BND.O",
    "BRKB": "https://m.stock.naver.com/worldstock/stock/BRKb/total",
    "DGRO": "https://m.stock.naver.com/worldstock/etf/DGRO.K",
    "DIA": "https://m.stock.naver.com/worldstock/etf/DIA",
    "DIVO": "https://m.stock.naver.com/worldstock/etf/DIVO.K",
    "GLD": "https://m.stock.naver.com/worldstock/etf/GLD",
    "GOOGL": "https://m.stock.naver.com/worldstock/stock/GOOGL.O/total",
    "IEF": "https://m.stock.naver.com/worldstock/etf/IEF.O",
    "IVV": "https://m.stock.naver.com/worldstock/etf/IVV",
    "IWM": "https://m.stock.naver.com/worldstock/etf/IWM",
    "JEPI": "https://m.stock.naver.com/worldstock/etf/JEPI.K",
    "JEPQ": "https://m.stock.naver.com/worldstock/etf/JEPQ.O",
    "META": "https://m.stock.naver.com/worldstock/stock/META.O/total",
    "MSFT": "https://m.stock.naver.com/worldstock/stock/MSFT.O/total",
    "NVDA": "https://m.stock.naver.com/worldstock/stock/NVDA.O/total",
    "O": "https://m.stock.naver.com/worldstock/stock/O/total",
    "QQQ": "https://m.stock.naver.com/worldstock/etf/QQQ.O",
    "QQQM": "https://m.stock.naver.com/worldstock/etf/QQQM.O",
    "QYLD": "https://m.stock.naver.com/worldstock/etf/QYLD.O",
    "RYLD": "https://m.stock.naver.com/worldstock/etf/RYLD.K",
    "SCHD": "https://m.stock.naver.com/worldstock/etf/SCHD.K",
    "SCHF": "https://m.stock.naver.com/worldstock/etf/SCHF.K",
    "SGOV": "https://m.stock.naver.com/worldstock/etf/SGOV.K",
    "SHY": "https://m.stock.naver.com/worldstock/etf/SHY.O",
    "SMH": "https://m.stock.naver.com/worldstock/etf/SMH.O",
    "SOXL": "https://m.stock.naver.com/worldstock/etf/SOXL.K",
    "SOXX": "https://m.stock.naver.com/worldstock/etf/SOXX.O",
    "SPY": "https://m.stock.naver.com/worldstock/etf/SPY",
    "TLT": "https://m.stock.naver.com/worldstock/etf/TLT.O",
    "TQQQ": "https://m.stock.naver.com/worldstock/etf/TQQQ.O",
    "TSLA": "https://m.stock.naver.com/worldstock/stock/TSLA.O/total",
    "VEA": "https://m.stock.naver.com/worldstock/etf/VEA",
    "VOO": "https://m.stock.naver.com/worldstock/etf/VOO",
    "VTI": "https://m.stock.naver.com/worldstock/etf/VTI",
    "VWO": "https://m.stock.naver.com/worldstock/etf/VWO",
    "VYM": "https://m.stock.naver.com/worldstock/etf/VYM",
    "XLK": "https://m.stock.naver.com/worldstock/etf/XLK",
    "XYLD": "https://m.stock.naver.com/worldstock/etf/XYLD.K",
}
