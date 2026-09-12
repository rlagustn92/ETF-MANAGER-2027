"""전술 JSON 저장/불러오기 + 슬롯 배치 저장/복원 + 잘못된 파일 처리 (인수인계서 88, 89, 115).

전술판이 FM 풍 세로 슬롯 스냅 방식으로 바뀌면서, 종목의 위치는 자유 좌표가 아니라
포지션 슬롯(slot, 예: "MC-C")으로 저장/복원됩니다. visual_x/visual_y 는 그 슬롯의 중심
좌표로 파생되며, 기존 x/y 키를 쓰는 파일도 "가장 가까운 슬롯"으로 자동 배치됩니다.
"""

import pytest

import config
import pitch_grid
from models.portfolio import Portfolio
from models.security import Security
from services import tactic_service


def _sample_portfolio() -> Portfolio:
    p = Portfolio(name="월배당 공격형", initial_capital_krw=100_000_000)
    p.add(Security(market="US", ticker="QQQ", name="Invesco QQQ Trust", target_weight=0.20))
    p.add(Security(market="US", ticker="JEPQ", name="JPMorgan Nasdaq Equity Premium Income ETF",
                   target_weight=0.20))
    p.add(Security(market="KR", ticker="005930", name="삼성전자", display_name="삼성전자",
                   currency="KRW", target_weight=0.10))
    return p


def test_roundtrip_preserves_core_fields_and_slot():
    p = _sample_portfolio()
    qqq_slot_before = next(s for s in p.securities if s.ticker == "QQQ").slot
    text = tactic_service.to_json(p)

    res = tactic_service.from_json(text)
    assert res.ok is True
    q = res.portfolio
    assert q.name == "월배당 공격형"
    assert q.initial_capital_krw == 100_000_000
    assert len(q.securities) == 3

    qqq = next(s for s in q.securities if s.ticker == "QQQ")
    assert qqq.target_weight == pytest.approx(0.20)
    assert qqq.slot == qqq_slot_before                       # 슬롯 배치 복원
    ex, ey = pitch_grid.center(qqq.slot)
    assert qqq.visual_x == pytest.approx(ex)                 # 좌표는 슬롯 중심에서 파생
    assert qqq.visual_y == pytest.approx(ey)

    sam = next(s for s in q.securities if s.ticker == "005930")
    assert sam.market == "KR"
    assert sam.display_name == "삼성전자"
    assert pitch_grid.is_slot(sam.slot)

    # 세 종목은 서로 다른 슬롯을 차지해야 함
    assert len({s.slot for s in q.securities}) == 3


def test_export_dict_has_app_year_positions_and_slot_keys():
    p = _sample_portfolio()
    d = p.to_dict()
    assert d[config.TACTIC_FILE_APP_KEY] == config.APP_YEAR
    assert isinstance(d["positions"], list)
    pos0 = d["positions"][0]
    assert "slot" in pos0
    # 구버전 호환용 x/y 키도 함께 기록 (인수인계서 88)
    assert "x" in pos0 and "y" in pos0


def test_legacy_free_xy_file_migrates_to_nearest_distinct_slots():
    # 인수인계서 88 의 JSON 예시 구조 (slot 없이 자유 좌표 x/y 만 있는 구버전 파일)
    example = {
        "app_year": 2027,
        "name": "월배당 공격형",
        "initial_capital_krw": 100000000,
        "positions": [
            {"market": "US", "ticker": "QQQ", "target_weight": 0.2, "x": 0.5, "y": 0.2,
             "distribution_enabled": True},
            {"market": "US", "ticker": "JEPQ", "target_weight": 0.2, "x": 0.5, "y": 0.55,
             "distribution_enabled": True},
            {"market": "KR", "ticker": "005930", "target_weight": 0.1, "x": 0.25, "y": 0.45,
             "distribution_enabled": True},
        ],
    }
    import json
    res = tactic_service.from_json(json.dumps(example))
    assert res.ok is True
    secs = res.portfolio.securities
    assert len(secs) == 3
    for s in secs:
        assert pitch_grid.is_slot(s.slot)
        ex, ey = pitch_grid.center(s.slot)
        assert s.visual_x == pytest.approx(ex)
        assert s.visual_y == pytest.approx(ey)
    assert len({s.slot for s in secs}) == 3   # 겹치지 않게 자동 배치


def test_legacy_duplicate_xy_resolves_to_different_slots():
    example = {
        "positions": [
            {"market": "US", "ticker": "AAA", "target_weight": 0.1, "x": 0.5, "y": 0.5},
            {"market": "US", "ticker": "BBB", "target_weight": 0.1, "x": 0.5, "y": 0.5},
            {"market": "US", "ticker": "CCC", "target_weight": 0.1, "x": 0.5, "y": 0.5},
        ],
    }
    import json
    res = tactic_service.from_json(json.dumps(example))
    assert res.ok is True
    slots = [s.slot for s in res.portfolio.securities]
    assert len(set(slots)) == 3   # 완전히 같은 좌표라도 서로 다른 슬롯으로 분산 배치


def test_assign_slot_swaps_when_target_occupied():
    p = Portfolio(name="swap", initial_capital_krw=1_000_000)
    p.add(Security(market="US", ticker="AAA", target_weight=0.0))
    p.add(Security(market="US", ticker="BBB", target_weight=0.0))
    a = next(s for s in p.securities if s.ticker == "AAA")
    b = next(s for s in p.securities if s.ticker == "BBB")
    a_slot, b_slot = a.slot, b.slot
    assert a_slot != b_slot

    p.assign_slot(a.id, b_slot)   # A 를 B 의 자리로 -> 서로 자리가 바뀌어야 함
    assert a.slot == b_slot
    assert b.slot == a_slot
    assert len({a.slot, b.slot}) == 2


def test_full_pitch_rejects_27th_security():
    # 슬롯 자체의 한계(26개)를 검증하려면 종목수 상한(max_squad_size)을 슬롯 수만큼 열어야 함
    p = Portfolio(name="full", initial_capital_krw=1_000_000,
                 max_squad_size=len(pitch_grid.all_slots()))
    for i in range(26):
        p.add(Security(market="US", ticker=f"T{i}", target_weight=0.0))
    assert len({s.slot for s in p.securities}) == 26
    with pytest.raises(ValueError):
        p.add(Security(market="US", ticker="OVERFLOW", target_weight=0.0))


def test_default_squad_size_is_eleven_like_a_football_team():
    p = Portfolio(name="squad", initial_capital_krw=1_000_000)
    assert p.max_squad_size == 11 == config.SQUAD_SIZE_DEFAULT
    for i in range(11):
        p.add(Security(market="US", ticker=f"S{i}", target_weight=0.0))
    assert len(p.securities) == 11
    with pytest.raises(ValueError, match="11"):
        p.add(Security(market="US", ticker="S11", target_weight=0.0))


def test_squad_size_toggle_expands_to_full_pitch():
    full = len(pitch_grid.all_slots())
    p = Portfolio(name="squad", initial_capital_krw=1_000_000, max_squad_size=full)
    for i in range(full):
        p.add(Security(market="US", ticker=f"F{i}", target_weight=0.0))
    assert len(p.securities) == full
    with pytest.raises(ValueError):
        p.add(Security(market="US", ticker="OVERFLOW", target_weight=0.0))


def test_max_squad_size_roundtrips_through_json():
    p = Portfolio(name="squad", initial_capital_krw=1_000_000, max_squad_size=26)
    d = p.to_dict()
    assert d["max_squad_size"] == 26

    import json
    res = tactic_service.from_json(json.dumps(d))
    assert res.ok is True
    assert res.portfolio.max_squad_size == 26


def test_squad_size_defaults_and_clamps_on_legacy_load():
    # max_squad_size 가 없는 구버전 파일 -> 기본값 11
    res1 = tactic_service.from_json('{"positions": []}')
    assert res1.ok is True
    assert res1.portfolio.max_squad_size == config.SQUAD_SIZE_DEFAULT

    # 기본 한도(11)보다 종목이 많은 파일을 불러오면, 있던 종목이 잘리지 않도록
    # 한도가 그 종목 수만큼 자동으로 올라가야 함
    import json
    positions = [{"market": "US", "ticker": f"L{i}", "target_weight": 0.0} for i in range(15)]
    res2 = tactic_service.from_json(json.dumps({"positions": positions}))
    assert res2.ok is True
    assert len(res2.portfolio.securities) == 15
    assert res2.portfolio.max_squad_size >= 15


@pytest.mark.parametrize("bad", [
    "{ not json",
    "[]",
    "123",
    '{"name": "x"}',                       # positions 없음
    '{"positions": "nope"}',               # positions 가 리스트 아님
    '{"positions": [{"ticker": "QQQ"}]}',  # market 없음
    '{"positions": [{"market": "US"}]}',   # ticker 없음
    '{"positions": [], "initial_capital_krw": "abc"}',  # 자본금 숫자 아님
])
def test_bad_files_do_not_crash(bad):
    res = tactic_service.from_json(bad)
    assert res.ok is False
    assert res.portfolio is None
    assert "전술 파일" in res.message or "자본금" in res.message or "항목" in res.message
