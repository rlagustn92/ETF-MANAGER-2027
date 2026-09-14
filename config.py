"""
ETF MANAGER - 중앙 설정 파일 (Central configuration)
=====================================================

이 프로젝트의 모든 "변경 가능성이 있는 값"은 이 파일 한 곳에 모읍니다.
다른 파일에 같은 값을 하드코딩하지 않습니다. (인수인계서 3, 107-2 항목)

연도 변경 방법
--------------
아래 APP_YEAR 한 줄만 바꾸면 프로그램 전체 명칭이 바뀝니다.

    APP_YEAR = 2027   ->   "ETF MANAGER 2027"
    APP_YEAR = 2028   ->   "ETF MANAGER 2028"

app.py, HTML <title>, 저장 파일명, README 표기 등은 모두 아래 값을 참조합니다.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

# =====================================================================
# 1. 프로그램 명칭 (연도 변경은 여기 한 줄)
# =====================================================================
APP_YEAR: int = 2027

# 프로그램 버전. 크든 작든 무언가 바꿀 때마다 맨 뒷자리를 1 올립니다
# (1.0.0 -> 1.0.1 -> 1.0.2 ...). 화면 맨 위 제목 옆에 표시됩니다.
APP_VERSION: str = "1.0.20"


def app_name() -> str:
    """화면/타이틀/파일명에서 쓰는 공식 명칭. 항상 APP_YEAR 에서 파생됩니다."""
    return f"ETF MANAGER {APP_YEAR}"


def app_name_with_icon() -> str:
    return f"⚽ {app_name()}"


def app_version_label() -> str:
    return f"v{APP_VERSION}"


# 제목 옆 "개발자 피드백/버그제보" 링크가 열 주소. 바꾸려면 여기 한 줄만 고치면 됩니다.
FEEDBACK_URL: str = "https://diycarebox.tistory.com/44"
FEEDBACK_LABEL: str = "개발자 피드백/버그제보/비회원댓글가능"

# 배포 주소. 📸 캡처 이미지 맨 아래에 찍혀서, 그 이미지가 커뮤니티로 퍼질 때
# 어디서 만든 건지 따라가게 됩니다. 배포 주소가 바뀌면 여기 한 줄만 고치세요.
APP_PUBLIC_URL: str = "etfmanager2027.streamlit.app"


# 편의 상수 (임포트 시점 계산). 연도 변경은 프로세스 재시작으로 반영됩니다.
# 코드에서는 가급적 app_name() / app_name_with_icon() 를 직접 호출하세요.
APP_NAME: str = app_name()
APP_NAME_WITH_ICON: str = app_name_with_icon()

# 전술 저장 파일(JSON)에 기록되는 스키마/앱 정보
TACTIC_FILE_APP_KEY: str = "app_year"
TACTIC_SCHEMA_VERSION: int = 1


# =====================================================================
# 2. 통화 / 금액 기본값
# =====================================================================
BASE_CURRENCY: str = "KRW"            # 포트폴리오 요약은 원화 기준으로 표시
SUPPORTED_CURRENCIES = ("KRW", "USD")

# 사용자가 처음 화면을 열었을 때 채워지는 기본 초기자본 (원)
# 어떤 금액이든 입력 가능하며, 이것은 단순 시작값일 뿐입니다.
DEFAULT_INITIAL_CAPITAL_KRW: int = 100_000_000


# =====================================================================
# 3. 매수 계산 기본 설정
# =====================================================================
# 1차 버전 기본값: 정수 주식만 매수 (소수점 매수 OFF)
FRACTIONAL_SHARES_DEFAULT: bool = False

# 최대 보유 종목 수 기본값. 축구 한 팀(11명)처럼 기본은 11개로 제한하고,
# 헤더의 확장 토글을 켜면 전술판 슬롯 전체(pitch_grid.all_slots() 개수, 26개)까지 늘어납니다.
SQUAD_SIZE_DEFAULT: int = 11

# 목표비중 편집 시 초기자본 한도를 강제할지 여부의 기본값.
# True(기본) = 종목 목표비중을 슬라이더/직접입력/수량입력으로 바꿀 때, 다른 종목들과의
#   합계가 100%(=초기자본)를 넘지 않도록 자동으로 잘라냅니다(사용자 요청으로 추가).
# 헤더의 "초기자본 초과 허용" 토글을 켜면 이 제한이 꺼지고, 기존처럼 자유롭게 입력하되
# 합계가 100%를 넘으면 경고만 표시합니다.
STRICT_CAPITAL_LIMIT_DEFAULT: bool = True

# 목표비중 합계 허용 범위
#  - 100% 초과: 오류
#  - 100% 미만: 허용 (나머지는 현금)
MAX_TOTAL_WEIGHT: float = 1.0
# 부동소수점 오차 허용치 (예: 0.30 + 0.70 이 1.0000000001 이 되는 경우)
WEIGHT_SUM_EPSILON: float = 1e-9


# =====================================================================
# 4. 분배금(배당) 계산 기본 설정
# =====================================================================
# 기본 계산 방식: 최근 12개월 실제 분배금 합계 (TTM = Trailing Twelve Months)
DISTRIBUTION_METHOD_DEFAULT: str = "auto_ttm"   # "auto_ttm" | "manual"
DISTRIBUTION_TTM_MONTHS: int = 12
# 종목별 "분배금 계산 포함" 기본값
DISTRIBUTION_ENABLED_DEFAULT: bool = True
# 화면에 항상 표시할 고지 문구
DISTRIBUTION_DISCLAIMER: str = "※ 최근 12개월 분배금 기준 단순 예상이며, 미래 분배금을 보장하지 않습니다."


# =====================================================================
# 5. 백테스트 기본 설정
# =====================================================================
# 사용자가 입력한 시작일이 거래일이 아닐 때: 입력일 "이후" 첫 거래일로 이동
BACKTEST_NON_TRADING_DAY_RULE: str = "next"     # "next" (권장)
# 1차 버전: 분배금은 현금 누적, 재투자 없음
BACKTEST_REINVEST_DISTRIBUTIONS: bool = False
# 1차 버전: 수수료/세금/슬리피지/환전비용 미반영
BACKTEST_DISCLAIMER: str = (
    "※ 수수료·거래세·세금·환전 스프레드·슬리피지는 반영하지 않은 단순 시뮬레이션입니다."
)


# =====================================================================
# 6. 데이터 provider / 캐시 설정
# =====================================================================
# 캐시 만료 시간(초). 일별 종가 기준 앱이므로 근거 없이 길게 잡지 않습니다.
CACHE_TTL_PRICE_SECONDS: int = 60 * 60 * 6       # 가격 히스토리: 6시간
CACHE_TTL_LATEST_PRICE_SECONDS: int = 60 * 15    # 최신가: 15분
CACHE_TTL_FX_SECONDS: int = 60 * 60              # 환율: 1시간
CACHE_TTL_DISTRIBUTION_SECONDS: int = 60 * 60 * 12  # 분배금 히스토리: 12시간
CACHE_TTL_SEARCH_SECONDS: int = 60 * 60 * 24     # 종목 검색 목록: 24시간

CACHE_DIR_NAME: str = ".cache"

# ---- 방문자 카운터 -------------------------------------------------------
# 배포 서버(Streamlit Cloud)는 앱이 잠들거나 재배포되면 파일이 초기화됩니다.
# 그래서 숫자를 서버에 적어두면 계속 0 으로 돌아가므로, 외부 카운터에 맡깁니다.
# 무료 서비스라 언제든 멈출 수 있으니 실패해도 앱은 그대로 동작해야 합니다.
COUNTER_ENABLED: bool = True
COUNTER_BASE_URL: str = "https://abacus.jasoncameron.dev"
COUNTER_NAMESPACE_DEFAULT: str = "etfmanager2027"
COUNTER_TIMEOUT_SECONDS: float = 2.5      # 느려도 화면을 오래 붙잡지 않도록 짧게

# 환율 티커/심볼 (USD -> KRW)
FX_PAIR_USDKRW: str = "USDKRW=X"     # yfinance 심볼. provider 구현 시 실행 검증.

# yfinance 가격 조회 시 명시적으로 설정할 옵션
#  - auto_adjust=False 로 "실제 종가(Close)"와 "조정종가(Adj Close)"를 분리해서 받습니다.
YFINANCE_AUTO_ADJUST: bool = False


# =====================================================================
# 7. 전술판(축구장) 포지션 그룹 / 슬롯 격자
# =====================================================================
# 전술판은 FM 풍 "세로 + 포지션 슬롯 스냅" 방식입니다 (화면 아래=우리 진영/GK, 위=공격 방향).
# 슬롯 격자(5칸 x 6라인)와 좌표 계산은 pitch_grid.py 에서 관리합니다.
DEFAULT_POSITION_GROUPS = ("ATTACK", "MIDFIELD", "DEFENSE", "GOALKEEPER")
POSITION_GROUP_LABELS_KR = {
    "ATTACK": "공격",
    "MIDFIELD": "미드필더",
    "DEFENSE": "수비",
    "GOALKEEPER": "골키퍼",
}

# 전술판 가로/세로 레이아웃 (사용자가 27인치 화면에서 직접 테스트해 확정한 값).
# PITCH_MID_COL_RATIO: 본문 3단 컬럼([좌, 중, 우]) 중 전술판이 들어가는 가운데 컬럼의 비율.
# PITCH_ASPECT_RATIO: 전술판의 세로/가로 비율. 클수록 세로로 길어짐 (기존 96/72 -> 1.06 으로 축소).
PITCH_MID_COL_RATIO: float = 1.7
PITCH_ASPECT_RATIO: float = 1.06


# =====================================================================
# 8. 표시 / 포맷
# =====================================================================
# ---- 시간대 -------------------------------------------------------------
# 화면에 "KST" 라고 적으므로 반드시 한국 시간으로 계산해야 합니다.
# datetime.now() 를 그냥 쓰면 "서버의 시간"이 나오는데, 배포 서버(Streamlit Cloud)는
# UTC 라서 9시간 어긋난 시각을 KST 라고 표시하게 됩니다. (실제로 있었던 버그)
# 한국은 서머타임이 없어서 고정 +9 로 충분하고, tzdata 설치 여부와 무관해 배포에 안전합니다.
KST = timezone(timedelta(hours=9))
TIMEZONE_LABEL: str = "KST"


def now_local() -> datetime:
    """화면 표시용 '지금' (한국 시간)."""
    return datetime.now(KST)


def today_local() -> date:
    """화면 표시용 '오늘' (한국 날짜)."""
    return now_local().date()


DATA_AS_OF_LABEL: str = "데이터 기준일"
LAST_UPDATED_LABEL: str = "마지막 업데이트"
NO_DATA_TEXT: str = "데이터 없음"
NEEDS_CHECK_TEXT: str = "확인 필요"

# 저장 파일명 접두사 (예: "ETF_MANAGER_<연도>_월배당공격형.json")
# 전술명은 사용자가 아무거나 칠 수 있고, 불러온 JSON 에 들어 있던 값일 수도 있습니다.
# 운영체제가 거부하는 이름이 만들어지면 "저장"을 눌러도 아무 일도 안 일어납니다.
FILENAME_PART_MAX: int = 60          # 전체 파일명이 100자를 넘지 않도록


def _safe_filename_part(tactic_name: str) -> str:
    name = (tactic_name or "").strip()
    # 1) 파일명에 못 쓰는 글자 제거.
    #    제어문자(줄바꿈·탭 등)도 반드시 빼야 합니다 -- 윈도우/맥 모두 거부합니다.
    #    (한 줄 입력칸에는 못 넣지만, 전술 JSON 을 손으로 고쳐 불러오면 들어옵니다)
    safe = "".join(c for c in name if c not in '<>:"/\\|?*' and ord(c) >= 32)
    safe = safe.replace(" ", "_").strip("_")
    # 2) 길이 제한. 안 걸면 전술명이 긴 경우 파일명이 OS 한계(255)를 넘어 저장이 실패합니다.
    if len(safe) > FILENAME_PART_MAX:
        safe = safe[:FILENAME_PART_MAX].rstrip("_")
    # 3) 점 처리. 점으로만 이뤄졌거나(".", "..") 점으로 끝나는 이름은 운영체제가 싫어하고,
    #    "/" 를 지우고 나면 "전술/../../etc" 가 "전술....etc" 처럼 점이 뭉치기도 합니다.
    safe = re.sub(r"\.{2,}", ".", safe).strip(".")
    return safe or "tactic"


def tactic_export_filename(tactic_name: str) -> str:
    return f"{app_name().replace(' ', '_')}_{_safe_filename_part(tactic_name)}.json"


def capture_image_filename(tactic_name: str) -> str:
    """📸 저장 버튼이 내려받는 PNG 파일 이름.

    날짜를 붙이는 이유: 같은 전술을 며칠 뒤에 다시 저장하면 가격·분배금이 달라진
    다른 그림인데, 이름이 같으면 브라우저가 "(1)" 을 붙여서 어느 게 언제 것인지
    알 수 없게 됩니다.
    """
    return (f"{app_name().replace(' ', '_')}_{_safe_filename_part(tactic_name)}"
            f"_{today_local():%Y%m%d}.png")
