"""
data/providers/us_seed.py  --  미국 종목 검색 시드 목록
=====================================================

미국 주식/ETF 는 오프라인 전체 목록이 없으므로, 인수인계서에 등장하는 대표 종목 +
자주 쓰이는 종목을 시드로 둡니다. (모두 실재하는 티커/명칭)

시드에 없는 티커는 search_provider 가 yfinance 로 "실제 조회해서" 확인 후 추가합니다.
(임의 생성 금지 -- 인수인계서 5, 117)

각 항목: (ticker, name, asset_type)  asset_type 은 참고용 분류일 뿐 점수가 아님(인수인계서 6).
"""

US_SEED: list[tuple[str, str, str]] = [
    # 브로드 지수
    ("VOO", "Vanguard S&P 500 ETF", "ETF"),
    ("SPY", "SPDR S&P 500 ETF Trust", "ETF"),
    ("IVV", "iShares Core S&P 500 ETF", "ETF"),
    ("QQQ", "Invesco QQQ Trust", "ETF"),
    ("QQQM", "Invesco NASDAQ 100 ETF", "ETF"),
    ("VTI", "Vanguard Total Stock Market ETF", "ETF"),
    ("DIA", "SPDR Dow Jones Industrial Average ETF", "ETF"),
    ("IWM", "iShares Russell 2000 ETF", "ETF"),
    # 레버리지 / 섹터
    ("TQQQ", "ProShares UltraPro QQQ (3x)", "ETF"),
    ("SOXX", "iShares Semiconductor ETF", "ETF"),
    ("SOXL", "Direxion Daily Semiconductor Bull 3x", "ETF"),
    ("SMH", "VanEck Semiconductor ETF", "ETF"),
    ("XLK", "Technology Select Sector SPDR", "ETF"),
    # 배당 / 커버드콜 / 현금흐름
    ("SCHD", "Schwab US Dividend Equity ETF", "ETF"),
    ("JEPI", "JPMorgan Equity Premium Income ETF", "ETF"),
    ("JEPQ", "JPMorgan Nasdaq Equity Premium Income ETF", "ETF"),
    ("DIVO", "Amplify CWP Enhanced Dividend Income ETF", "ETF"),
    ("QYLD", "Global X NASDAQ 100 Covered Call ETF", "ETF"),
    ("XYLD", "Global X S&P 500 Covered Call ETF", "ETF"),
    ("RYLD", "Global X Russell 2000 Covered Call ETF", "ETF"),
    ("VYM", "Vanguard High Dividend Yield ETF", "ETF"),
    ("DGRO", "iShares Core Dividend Growth ETF", "ETF"),
    ("O", "Realty Income Corporation", "STOCK"),
    # 채권 / 현금성
    ("TLT", "iShares 20+ Year Treasury Bond ETF", "ETF"),
    ("IEF", "iShares 7-10 Year Treasury Bond ETF", "ETF"),
    ("SHY", "iShares 1-3 Year Treasury Bond ETF", "ETF"),
    ("SGOV", "iShares 0-3 Month Treasury Bond ETF", "ETF"),
    ("BIL", "SPDR Bloomberg 1-3 Month T-Bill ETF", "ETF"),
    ("BND", "Vanguard Total Bond Market ETF", "ETF"),
    # 해외 / 기타
    ("VEA", "Vanguard FTSE Developed Markets ETF", "ETF"),
    ("VWO", "Vanguard FTSE Emerging Markets ETF", "ETF"),
    ("GLD", "SPDR Gold Shares", "ETF"),
    ("SCHF", "Schwab International Equity ETF", "ETF"),
    # 대형 개별주 (예시)
    ("AAPL", "Apple Inc.", "STOCK"),
    ("MSFT", "Microsoft Corporation", "STOCK"),
    ("NVDA", "NVIDIA Corporation", "STOCK"),
    ("GOOGL", "Alphabet Inc. Class A", "STOCK"),
    ("AMZN", "Amazon.com, Inc.", "STOCK"),
    ("META", "Meta Platforms, Inc.", "STOCK"),
    ("TSLA", "Tesla, Inc.", "STOCK"),
    ("BRK-B", "Berkshire Hathaway Inc. Class B", "STOCK"),
]
