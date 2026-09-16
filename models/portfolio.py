"""
models/portfolio.py  --  전술(포트폴리오) 데이터 모델
=====================================================

전술 = 전술명 + 초기자본 + 종목 목록(+ 각 종목의 비중/좌표/분배금 설정).
JSON 내보내기/불러오기를 1차 저장 방식으로 사용합니다. (인수인계서 87~89)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import config
import pitch_grid
from models import numbers
from models.security import Security


@dataclass
class Portfolio:
    name: str = "새 전술"
    initial_capital_krw: float = config.DEFAULT_INITIAL_CAPITAL_KRW
    fractional_shares: bool = config.FRACTIONAL_SHARES_DEFAULT
    # 최대 보유 종목 수. 기본은 축구 한 팀(11명), 헤더 토글로 전체 슬롯(26개)까지 확장 가능.
    max_squad_size: int = config.SQUAD_SIZE_DEFAULT
    # True(기본) = 종목별 목표비중 합계가 100%(초기자본)를 넘지 않도록 편집 시점에 자동으로
    # 잘라냅니다. 헤더 토글로 끄면 자유롭게 입력하되 초과 시 경고만 표시합니다(사용자 요청).
    strict_capital_limit: bool = config.STRICT_CAPITAL_LIMIT_DEFAULT
    securities: list[Security] = field(default_factory=list)

    # ---- 종목 관리 ----
    def add(self, sec: Security) -> None:
        if any(s.market == sec.market and s.ticker == sec.ticker for s in self.securities):
            raise ValueError(f"이미 추가된 종목입니다: {sec.market}:{sec.ticker}")
        if len(self.securities) >= self.max_squad_size:
            raise ValueError(
                f"최대 {self.max_squad_size}개 종목까지 담을 수 있습니다. "
                f"헤더의 확장 토글을 켜면 전술판 슬롯 전체"
                f"({len(pitch_grid.all_slots())}개)까지 늘릴 수 있어요."
            )
        # 슬롯이 비었거나 이미 점유된 슬롯이면 빈 슬롯을 자동 배정
        used = self.used_slots()
        if not pitch_grid.is_slot(sec.slot) or sec.slot in used:
            free = pitch_grid.first_free_slot(used, pitch_grid.guess_row(sec.ticker))
            if free is None:
                raise ValueError("전술판에 빈 포지션 슬롯이 없습니다. (최대 26종목)")
            sec.place_in_slot(free)
        self.securities.append(sec)

    def remove(self, security_id: str) -> None:
        self.securities = [s for s in self.securities if s.id != security_id]

    def get(self, security_id: str) -> Security | None:
        return next((s for s in self.securities if s.id == security_id), None)

    def used_slots(self, exclude_id: str | None = None) -> set[str]:
        return {s.slot for s in self.securities
                if s.id != exclude_id and pitch_grid.is_slot(s.slot)}

    def remaining_weight_budget_pct(self, exclude_id: str | None = None) -> float:
        """exclude_id 를 제외한 나머지 종목들의 목표비중 합계를 뺀 남은 여유(%, 0~100).

        strict_capital_limit 모드에서 "이 종목에 최대 몇 % 까지 줄 수 있는지" 계산할 때 씁니다.
        """
        others = sum(s.target_weight for s in self.securities if s.id != exclude_id)
        return max(0.0, 100.0 - others * 100.0)

    def clamp_weight_pct(self, sec_id: str, desired_pct: float) -> tuple[float, bool]:
        """목표비중(%) 편집값을 정책에 맞게 보정. (보정된 값, 잘렸는지 여부) 를 반환.

        strict_capital_limit 이 꺼져 있으면 0~100 범위로만 자릅니다(기존 동작).
        켜져 있으면(기본값) 다른 종목들과의 합계가 100% 를 넘지 않도록 추가로 자릅니다.
        """
        pct = max(0.0, min(100.0, float(desired_pct)))
        # 시드 전체(100%)보다 큰 값을 요청한 경우도 "잘렸다"고 알려야 합니다.
        # 슬라이더는 최대가 100% 라 이런 일이 없지만, 금액을 직접 적는 칸에서는
        # 시드보다 큰 금액을 그냥 적을 수 있어서 조용히 줄어들면 안 됩니다.
        over_seed = float(desired_pct) > 100.0
        if not self.strict_capital_limit:
            return pct, over_seed
        cap = self.remaining_weight_budget_pct(exclude_id=sec_id)
        if pct > cap + 1e-9:
            return cap, True
        return pct, over_seed

    def assign_slot(self, security_id: str, slot_id: str) -> None:
        """종목을 슬롯으로 이동. 슬롯이 다른 종목에 점유돼 있으면 서로 자리를 바꿉니다(스왑)."""
        if not pitch_grid.is_slot(slot_id):
            return
        mover = self.get(security_id)
        if mover is None:
            return
        origin = mover.slot
        occupant = next((s for s in self.securities
                         if s.id != security_id and s.slot == slot_id), None)
        mover.place_in_slot(slot_id)
        if occupant is not None:
            if pitch_grid.is_slot(origin):
                occupant.place_in_slot(origin)
            else:
                free = pitch_grid.first_free_slot(self.used_slots(),
                                                  pitch_grid.guess_row(occupant.ticker))
                if free is not None:
                    occupant.place_in_slot(free)

    # ---- 직렬화 (인수인계서 88 의 JSON 구조와 호환) ----
    def to_dict(self) -> dict:
        return {
            config.TACTIC_FILE_APP_KEY: config.APP_YEAR,          # "app_year": 2027
            "schema_version": config.TACTIC_SCHEMA_VERSION,
            "name": self.name,
            "initial_capital_krw": self.initial_capital_krw,
            "fractional_shares": self.fractional_shares,
            "max_squad_size": self.max_squad_size,
            "strict_capital_limit": self.strict_capital_limit,
            "positions": [_to_position_dict(s) for s in self.securities],
        }

    @staticmethod
    def from_dict(d: dict) -> "Portfolio":
        """예전부터 쓰던 입구. 고친 내용은 버립니다."""
        portfolio, _ = Portfolio.load(d)
        return portfolio

    @staticmethod
    def load(d: dict) -> tuple["Portfolio", list[str]]:
        """전술 파일을 읽고 **(전술, 고친 내용 목록)** 을 돌려줍니다.

        이상한 값이 있어도 파일을 통째로 거절하지 않습니다. 남의 전술을 받아
        열어보는 게 이 앱의 주된 공유 방법인데, 값 하나 때문에 아무것도 못 열면
        받은 사람 입장에서는 그냥 고장난 앱입니다.

        대신 **조용히 고치지도 않습니다.** 무엇을 어떻게 바꿨는지 돌려주고,
        화면에서 그대로 보여줍니다. ("3번째 종목의 비중이 숫자가 아니어서...")
        """
        issues: list[str] = []
        if not isinstance(d, dict):
            raise ValueError("전술 파일의 최상위 구조가 올바르지 않습니다.")
        positions = d.get("positions")
        if not isinstance(positions, list):
            raise ValueError("전술 파일에 'positions' 목록이 없습니다.")
        secs: list[Security] = []
        for i, p in enumerate(positions):
            try:
                secs.append(_from_position_dict(p))
            except Exception as e:  # 개별 항목 오류가 전체를 죽이지 않도록 메시지 명확화
                raise ValueError(f"{i + 1}번째 종목 항목이 올바르지 않습니다: {e}") from e
            if isinstance(p, dict):
                issues.extend(_position_issues(i, p, secs[-1]))

        _migrate_slots(secs)   # 자유 좌표(x/y) 전술 -> 가장 가까운 슬롯으로 자동 배치

        raw_cap = d.get("initial_capital_krw", config.DEFAULT_INITIAL_CAPITAL_KRW)
        if not numbers.is_finite_number(raw_cap):
            raise ValueError("initial_capital_krw 값이 숫자가 아닙니다.")
        # 음수 시드는 화면 입력칸으로는 못 만들지만 파일로는 들어옵니다.
        # 그대로 두면 데이터에 음수가 남아 계산 곳곳에서 이상하게 새어 나옵니다.
        cap = numbers.safe_float(raw_cap, default=config.DEFAULT_INITIAL_CAPITAL_KRW,
                                 minimum=0.0)
        if cap != float(raw_cap):
            issues.append(f"내 시드가 {float(raw_cap):,.0f}원이라 0원으로 맞췄습니다.")

        max_squad = d.get("max_squad_size", config.SQUAD_SIZE_DEFAULT)
        try:
            max_squad = int(max_squad)
        except (TypeError, ValueError):
            max_squad = config.SQUAD_SIZE_DEFAULT
        full = len(pitch_grid.all_slots())
        # 저장된 종목 수가 기본 한도보다 많으면(예: 확장 상태에서 저장한 구버전 파일)
        # 기존 종목이 잘리지 않도록 한도를 그 수만큼 자동으로 올려줌
        max_squad = max(1, min(full, max(max_squad, len(secs))))

        portfolio = Portfolio(
            name=str(d.get("name", "불러온 전술")),
            initial_capital_krw=cap,
            fractional_shares=bool(d.get("fractional_shares", config.FRACTIONAL_SHARES_DEFAULT)),
            max_squad_size=max_squad,
            strict_capital_limit=bool(d.get("strict_capital_limit",
                                            config.STRICT_CAPITAL_LIMIT_DEFAULT)),
            securities=secs,
        )
        return portfolio, issues


def _migrate_slots(secs: list[Security]) -> None:
    """각 종목을 유효한 고유 슬롯에 배치.

    - slot 이 유효하고 아직 안 쓰였으면 그대로 사용.
    - 아니면(자유 좌표만 있는 기존 파일 등) visual_x/visual_y 에서 가장 가까운 슬롯을 찾고,
      이미 점유됐으면 그 근처의 빈 슬롯으로 밀어냅니다.
    """
    used: set[str] = set()
    # 1차: 파일에 이미 유효·고유한 slot 이 있는 종목 확정
    for s in secs:
        if pitch_grid.is_slot(s.slot) and s.slot not in used:
            used.add(s.slot)
            s.place_in_slot(s.slot)
        else:
            s.slot = ""
    # 2차: 나머지를 가장 가까운(비어 있는) 슬롯에 배치
    for s in secs:
        if s.slot:
            continue
        want = pitch_grid.nearest(s.visual_x, s.visual_y)
        if want in used:
            want = pitch_grid.first_free_slot(used, pitch_grid.split(want)[0])
        if want is None:
            want = pitch_grid.first_free_slot(used)
        if want is None:
            continue  # 26개 초과 -- 배치 불가(그대로 둠)
        used.add(want)
        s.place_in_slot(want)


def _to_position_dict(s: Security) -> dict:
    d = s.to_dict()
    # 인수인계서 88 예시 키(x, y)도 함께 기록해 가독성을 높임
    d["x"] = d["visual_x"]
    d["y"] = d["visual_y"]
    return d


def _position_issues(index: int, raw: dict, sec: Security) -> list[str]:
    """파일에 적힌 값과 실제로 담긴 값이 다르면, 무엇이 달라졌는지 문장으로 만듭니다.

    Security 가 이미 이상한 값을 안전하게 바꿔서 담아둔 뒤입니다. 여기서는
    "조용히 바뀐 것"을 찾아내 사용자에게 알릴 말만 만듭니다.
    """
    out: list[str] = []
    nth = f"{index + 1}번째 종목({sec.ticker or '?'})"

    if "target_weight" in raw and not numbers.is_finite_number(raw["target_weight"]):
        out.append(f"{nth}의 비중이 숫자가 아니어서(`{raw['target_weight']!r}`) 0% 로 두었습니다.")
    elif "target_weight" in raw and float(raw["target_weight"]) < 0:
        out.append(f"{nth}의 비중이 음수여서 0% 로 두었습니다.")

    for key, label in (("manual_ttm_per_share", "직접 입력한 주당 분배금"),
                       ("manual_price", "직접 입력한 1주 가격")):
        v = raw.get(key)
        if v is not None and not numbers.is_finite_number(v):
            out.append(f"{nth}의 {label}이 숫자가 아니어서 비웠습니다. 자동 조회를 씁니다.")
    return out


def _from_position_dict(p: dict) -> Security:
    if not isinstance(p, dict):
        raise ValueError("종목 항목이 객체(dict)가 아닙니다.")
    return Security.from_dict(p)
