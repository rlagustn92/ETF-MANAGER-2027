"""
services/slot_service.py  --  전술 슬롯(여러 개 저장) + ZIP 백업
================================================================

왜 "자동 저장" 이 아니라 "슬롯" 인가
------------------------------------
공격형 하나, 배당형 하나를 같이 굴리는 사람에게 **저장 칸이 하나뿐인 자동 저장은
반쪽**입니다. 그래서 처음부터 칸을 여러 개로 만듭니다. 어차피 저장을 만들면
칸을 늘리는 건 목록 하나 더 두는 일이라, 나중에 붙이는 것보다 품이 덜 듭니다.

슬롯과 JSON 파일은 역할이 다릅니다
----------------------------------
    슬롯   : 이 브라우저 안에서 매일 왔다 갔다 하며 비교하는 용도. 손이 안 감.
    JSON   : 남에게 주기 · 다른 기기로 옮기기 · 백업. 어디로든 갈 수 있음.

둘을 섞으면 둘 다 어정쩡해집니다. 슬롯은 브라우저를 못 벗어나고,
파일은 매번 손이 갑니다. 그래서 **둘 다** 있어야 합니다.

왜 ZIP 인가
-----------
슬롯 3개를 각각 파일로 내려받으려면 다운로드가 3번 일어나는데, 크롬이
"이 사이트에서 여러 파일을 다운로드하려고 합니다" 허용 창을 띄웁니다. 딸깍 한 번이
두 번이 되고, 거부하면 첫 파일만 받아집니다. ZIP 으로 묶으면 파일이 하나라
그 창이 안 뜨고, 압축을 풀면 원하던 대로 이름별 파일이 나옵니다.
되돌릴 때도 ZIP 을 통째로 올리면 **슬롯 이름까지 한 번에** 복원됩니다.
"""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass, field

import config
from models import numbers
from models.portfolio import Portfolio

# 슬롯 칸 수. 늘리는 건 이 숫자 하나지만, 슬롯이 많아지면 고르는 데 시간이 걸려서
# "왔다 갔다 하며 비교한다"는 목적에서 멀어집니다.
MAX_SLOTS = 3

# 브라우저에 저장하는 꾸러미의 형식 번호. 구조를 바꿀 때 올리고, 읽는 쪽에서
# 모르는 번호면 조용히 무시합니다(옛날 데이터 때문에 앱이 죽으면 안 됨).
STORE_VERSION = 1

DEFAULT_SLOT_NAME = "새 전술"


@dataclass
class Slot:
    """저장된 전술 한 칸. tactic 은 Portfolio.to_dict() 결과입니다."""
    name: str = DEFAULT_SLOT_NAME
    tactic: dict = field(default_factory=dict)

    @property
    def security_count(self) -> int:
        positions = self.tactic.get("positions")
        return len(positions) if isinstance(positions, list) else 0

    def to_portfolio(self) -> Portfolio:
        """이 칸을 실제 전술로 되살립니다. 내용이 깨져 있으면 빈 전술을 돌려줍니다."""
        try:
            portfolio, _ = Portfolio.load(self.tactic)
            return portfolio
        except Exception:
            return empty_portfolio(self.name)


def empty_portfolio(name: str = DEFAULT_SLOT_NAME) -> Portfolio:
    return Portfolio(name=name or DEFAULT_SLOT_NAME,
                     initial_capital_krw=config.DEFAULT_INITIAL_CAPITAL_KRW)


def slot_from_portfolio(portfolio: Portfolio) -> Slot:
    return Slot(name=portfolio.name or DEFAULT_SLOT_NAME, tactic=portfolio.to_dict())


# 슬롯 탭에 들어갈 수 있는 이름 길이. 버튼이 좁아서 이보다 길면 줄여야 합니다.
SLOT_LABEL_MAX = 10


def slot_label(name: str, count: int) -> str:
    """슬롯 탭 글자. 이름이 길면 줄이고 종목 수를 괄호로 붙입니다.

    그냥 자르면 "월 100만원 · 1억 예시" 가 "월 100만원 · " 에서 끊기고, 뒤에 구분점이
    또 붙어서 "월 100만원 · · 9" 처럼 **고장난 것처럼** 보입니다.
    끝에 남은 구분점을 털어내고 줄임표를 붙입니다.
    """
    short = (name or DEFAULT_SLOT_NAME).strip() or DEFAULT_SLOT_NAME
    if len(short) > SLOT_LABEL_MAX:
        short = short[:SLOT_LABEL_MAX].rstrip(" ·-_,") + "…"
    return f"{short} ({count})"


def unique_name(existing: list[Slot], base: str = DEFAULT_SLOT_NAME) -> str:
    """이미 있는 이름과 안 겹치는 이름. 슬롯이 전부 "새 전술" 이면 고를 수가 없습니다."""
    taken = {s.name for s in existing}
    if base not in taken:
        return base
    for i in range(2, MAX_SLOTS + 2):
        candidate = f"{base} {i}"
        if candidate not in taken:
            return candidate
    return base


# ---------------------------------------------------------------------
# 브라우저 저장소에 넣을 문자열
# ---------------------------------------------------------------------
@dataclass
class StoreState:
    """브라우저에 저장하는 것 전부.

    목표(goal_monthly_krw)가 슬롯 **밖에** 있는 이유
    -----------------------------------------------
    "월 100만원 받고 싶다" 는 소망이지 전술의 속성이 아닙니다. 슬롯을 현재안 →
    공격안으로 바꿔도 목표는 그대로 남아야, **"공격안으로 바꾸니 41% → 78% 가
    되네"** 가 보입니다. 목표가 슬롯마다 따로면 그 비교가 아예 성립하지 않습니다.
    """
    slots: list[Slot] = field(default_factory=list)
    active: int = 0
    goal_monthly_krw: float = 0.0


def dumps(state: StoreState) -> str:
    return json.dumps(
        {
            "v": STORE_VERSION,
            "app": config.APP_YEAR,
            "active": max(0, min(int(state.active), max(0, len(state.slots) - 1))),
            "goal": float(state.goal_monthly_krw or 0.0),
            "slots": [{"name": s.name, "tactic": s.tactic} for s in state.slots],
        },
        ensure_ascii=False, separators=(",", ":"),
    )


def loads(text: str | None) -> StoreState:
    """저장해 둔 문자열을 읽습니다. **어떤 쓰레기가 와도 예외를 던지지 않습니다.**

    사용자의 브라우저에 있던 값이라 우리가 통제할 수 없고, 여기서 예외가 나면
    앱이 아예 안 뜹니다. 못 읽으면 빈 상태를 돌려주고 새로 시작하는 게 맞습니다.
    """
    empty = StoreState()
    if not text:
        return empty
    try:
        data = json.loads(text)
    except Exception:
        return empty
    if not isinstance(data, dict) or data.get("v") != STORE_VERSION:
        return empty

    raw_slots = data.get("slots")
    if not isinstance(raw_slots, list):
        return empty

    slots: list[Slot] = []
    for item in raw_slots[:MAX_SLOTS]:
        if not isinstance(item, dict):
            continue
        tactic = item.get("tactic")
        if not isinstance(tactic, dict):
            continue
        name = str(item.get("name") or DEFAULT_SLOT_NAME)[:40]
        slots.append(Slot(name=name, tactic=tactic))

    if not slots:
        return empty
    try:
        active = int(data.get("active") or 0)
    except (TypeError, ValueError):
        active = 0
    return StoreState(
        slots=slots,
        active=max(0, min(active, len(slots) - 1)),
        goal_monthly_krw=numbers.safe_float(data.get("goal"), default=0.0, minimum=0.0),
    )


# ---------------------------------------------------------------------
# ZIP 백업
# ---------------------------------------------------------------------
def zip_filename(count: int) -> str:
    return (f"{config.app_name().replace(' ', '_')}_전술{count}개"
            f"_{config.today_local():%Y%m%d}.zip")


def to_zip(slots: list[Slot]) -> bytes:
    """슬롯들을 ZIP 한 덩어리로. 안에는 슬롯마다 JSON 파일 하나씩 들어갑니다."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        used: set[str] = set()
        for slot in slots:
            name = config.tactic_export_filename(slot.name)
            # 전술명이 같으면 파일명도 같아집니다. 압축 파일 안에 같은 이름이 둘
            # 있으면 푸는 쪽에서 하나가 덮어써집니다.
            stem, dot, ext = name.rpartition(".")
            n = 2
            while name in used:
                name = f"{stem}_{n}{dot}{ext}"
                n += 1
            used.add(name)
            zf.writestr(name, json.dumps(slot.tactic, ensure_ascii=False, indent=2))
    return buffer.getvalue()


@dataclass
class ImportResult:
    ok: bool
    slots: list[Slot] = field(default_factory=list)
    replace_all: bool = False     # True = 슬롯 전체를 갈아끼움 (ZIP 백업 복원)
    message: str = ""


def read_upload(filename: str, data: bytes) -> ImportResult:
    """올린 파일을 슬롯으로. 전술 JSON 한 개도, 백업 ZIP 도 받습니다."""
    from services import tactic_service   # 순환 import 방지 (tactic_service 가 가벼움)

    if (filename or "").lower().endswith(".zip"):
        return _read_zip(data, tactic_service)

    res = tactic_service.from_json(data)
    if not res.ok:
        return ImportResult(False, message=res.message)
    return ImportResult(True, slots=[slot_from_portfolio(res.portfolio)],
                        replace_all=False, message=res.message)


def _read_zip(data: bytes, tactic_service) -> ImportResult:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except Exception:
        return ImportResult(False, message="ZIP 파일을 열 수 없습니다. 파일이 깨졌을 수 있어요.")

    slots: list[Slot] = []
    problems: list[str] = []
    with zf:
        names = [n for n in sorted(zf.namelist())
                 if n.lower().endswith(".json") and not n.endswith("/")]
        if not names:
            return ImportResult(False, message="ZIP 안에 전술 JSON 파일이 없습니다.")
        for name in names[:MAX_SLOTS]:
            try:
                raw = zf.read(name)
            except Exception:
                problems.append(f"{name}: 읽을 수 없습니다.")
                continue
            res = tactic_service.from_json(raw)
            if not res.ok:
                problems.append(f"{name}: {res.message}")
                continue
            slots.append(slot_from_portfolio(res.portfolio))
        skipped = len(names) - min(len(names), MAX_SLOTS)

    if not slots:
        return ImportResult(False, message="ZIP 안의 전술을 하나도 읽지 못했습니다.\n\n"
                                           + "\n".join(f"- {p}" for p in problems))

    notes = [f"전술 {len(slots)}개를 불러왔습니다."]
    if skipped:
        notes.append(f"슬롯은 {MAX_SLOTS}칸까지라 {skipped}개는 건너뛰었습니다.")
    notes += problems
    return ImportResult(True, slots=slots, replace_all=True, message=" ".join(notes))
