"""
models/security.py  --  종목(Security) 데이터 모델 (인수인계서 20)
==================================================================

축구장 배치는 FM 풍 세로 전술판의 "포지션 슬롯"(pitch_grid.py) 에 스냅됩니다.
- slot            : 슬롯 id (예: "ST-C", "MC-L", "GK-C"). 배치의 기준.
- visual_x/visual_y: slot 중심의 정규화 좌표. slot 에서 파생되며, 기존 JSON 포맷(x/y)과 호환됩니다.
- default_position_group: slot 이 속한 내부 그룹(ATTACK/MIDFIELD/DEFENSE/GOALKEEPER, 인수인계서 9).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict

import pitch_grid

# market 값
MARKET_US = "US"
MARKET_KR = "KR"

# 분배금 계산 방식
DIST_METHOD_AUTO = "auto_ttm"   # 최근 12개월 실제 분배금 합계
DIST_METHOD_MANUAL = "manual"   # 사용자가 직접 입력


@dataclass
class Security:
    # --- 식별 ---
    market: str                          # "US" | "KR"
    ticker: str                          # 예: "QQQ", "005930"
    name: str = ""                       # 정식 명칭 (예: "삼성전자")
    display_name: str = ""               # 아이콘 표시명 (짧게, 인수인계서 16)
    # 전술판 유니폼 아래 이름표에 찍을 글자를 사용자가 직접 정한 경우.
    # 비어 있으면 pitch_kit 이 정식 이름을 자동으로 줄여서 씁니다.
    # 자동 축약은 단어 사전 기반이라 새로 상장한 ETF 는 못 줄일 수 있고, 줄인 결과가
    # 마음에 안 들 수도 있어서 마지막 수단으로 직접 고칠 길을 열어 둡니다.
    card_label: str = ""
    currency: str = "USD"                # "USD" | "KRW"
    asset_type: str = "ETF"              # "ETF" | "STOCK" (참고용, 점수 아님)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    # --- 축구장 배치 (슬롯 스냅) ---
    slot: str = ""                             # 예: "MC-C". 비어 있으면 미배치
    default_position_group: str = "MIDFIELD"   # ATTACK/MIDFIELD/DEFENSE/GOALKEEPER
    visual_x: float = 0.5                      # slot 중심의 x (0=왼쪽 ~ 1=오른쪽)
    visual_y: float = 0.5                      # slot 중심의 y (0=위/공격 ~ 1=아래/우리골문)

    # --- 사용자 입력 ---
    target_weight: float = 0.0                 # 목표비중 (비율, 0.20 == 20%)
    distribution_enabled: bool = True          # 분배금 계산 포함 여부 (인수인계서 37)
    distribution_method: str = DIST_METHOD_AUTO
    manual_ttm_per_share: float | None = None  # 직접 입력한 최근 12개월 주당 분배금
    manual_price: float | None = None          # 자동 조회 실패 시 수동 가격 (해당 통화 기준)

    # --- 계산 결과 캐시 (서비스가 채움, 저장은 하지 않아도 됨) ---
    actual_shares: float = 0.0
    actual_investment: float = 0.0             # 기준통화(KRW)
    price_source: str = ""                     # "yfinance" | "FinanceDataReader" | "manual" | ""

    def __post_init__(self) -> None:
        self.ticker = str(self.ticker).strip()
        if not self.display_name:
            self.display_name = self.name or self.ticker
        if not self.name:
            self.name = self.display_name or self.ticker
        self.visual_x = _clamp01(self.visual_x)
        self.visual_y = _clamp01(self.visual_y)
        # slot 이 지정돼 있으면 좌표/그룹을 슬롯 기준으로 정규화
        if pitch_grid.is_slot(self.slot):
            self.place_in_slot(self.slot)

    # ---- 슬롯 배치 ----
    def place_in_slot(self, slot_id: str) -> None:
        """이 종목을 슬롯에 배치하고 좌표/그룹을 슬롯 기준으로 맞춥니다."""
        if not pitch_grid.is_slot(slot_id):
            return
        self.slot = slot_id
        self.visual_x, self.visual_y = pitch_grid.center(slot_id)
        self.default_position_group = pitch_grid.group_of(slot_id)

    # ---- 직렬화 (전술 저장/불러오기, 인수인계서 86~89) ----
    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ("actual_shares", "actual_investment", "price_source"):
            d.pop(k, None)
        return d

    @staticmethod
    def from_dict(d: dict) -> "Security":
        allowed = {
            "market", "ticker", "name", "display_name", "card_label",
            "currency", "asset_type", "id",
            "slot", "default_position_group", "visual_x", "visual_y",
            "target_weight", "distribution_enabled", "distribution_method",
            "manual_ttm_per_share", "manual_price",
        }
        # 인수인계서 88 의 JSON 예시는 x/y 키를 쓰므로 둘 다 허용
        data = {k: v for k, v in d.items() if k in allowed}
        if "visual_x" not in data and "x" in d:
            data["visual_x"] = d["x"]
        if "visual_y" not in data and "y" in d:
            data["visual_y"] = d["y"]
        if "market" not in data:
            raise ValueError("종목 항목에 'market' 이 없습니다.")
        if "ticker" not in data:
            raise ValueError("종목 항목에 'ticker' 가 없습니다.")
        return Security(**data)


def _clamp01(v: float) -> float:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, v))
