"""전술 슬롯 + ZIP 백업 테스트 (네트워크 없음).

지키려는 것
-----------
1. **브라우저에서 온 문자열 때문에 앱이 죽지 않는다.** 저장된 값은 사용자의
   브라우저에 있던 것이라 우리가 통제할 수 없습니다. 여기서 예외가 나면 앱이
   아예 안 뜹니다.
2. **저장이 안 되는 브라우저에서도 앱은 멀쩡히 돈다.** 컴포넌트가 None 을
   돌려주는 상황(= AppTest 가 그대로 재현하는 상황)에서 모든 기능이 살아 있어야 합니다.
3. **슬롯을 옮겨 다녀도 각 칸의 내용이 안 섞인다.**
"""

from __future__ import annotations

import io
import json
import pathlib
import zipfile

import pytest
from streamlit.testing.v1 import AppTest

import config
import presets
from models.portfolio import Portfolio
from models.security import Security
from services import slot_service, tactic_service

APP_PATH = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")


def _portfolio(name: str, tickers: list[str]) -> Portfolio:
    p = Portfolio(name=name, initial_capital_krw=10_000_000)
    for i, t in enumerate(tickers):
        p.add(Security(market="US", ticker=t, currency="USD",
                       target_weight=0.1 * (i + 1)))
    return p


def _slot(name: str, tickers: list[str]) -> slot_service.Slot:
    return slot_service.slot_from_portfolio(_portfolio(name, tickers))


# =====================================================================
# 저장 문자열 — 무엇이 와도 안 죽는다
# =====================================================================
def _store(slots, active=0, goal=0.0) -> slot_service.StoreState:
    return slot_service.StoreState(slots=slots, active=active, goal_monthly_krw=goal)


def test_dumps_loads_round_trip():
    slots = [_slot("현재안", ["SCHD", "JEPQ"]), _slot("공격안", ["QQQI"])]
    got = slot_service.loads(slot_service.dumps(_store(slots, 1)))
    assert [s.name for s in got.slots] == ["현재안", "공격안"]
    assert got.active == 1
    assert [s.security_count for s in got.slots] == [2, 1]
    assert [x.ticker for x in got.slots[0].to_portfolio().securities] == ["SCHD", "JEPQ"]


def test_the_goal_rides_along_with_the_slots():
    """목표는 전술이 아니라 사람의 것이라 슬롯 바깥에 따로 저장됩니다."""
    slots = [_slot("현재안", ["SCHD"])]
    got = slot_service.loads(slot_service.dumps(_store(slots, 0, goal=1_000_000)))
    assert got.goal_monthly_krw == 1_000_000


@pytest.mark.parametrize("bad_goal", [None, "많이", float("nan"), float("inf"), -500])
def test_a_broken_goal_becomes_zero_not_a_crash(bad_goal):
    slots = [_slot("현재안", ["SCHD"])]
    text = json.dumps({"v": slot_service.STORE_VERSION, "active": 0, "goal": bad_goal,
                       "slots": [{"name": "현재안", "tactic": slots[0].tactic}]})
    assert slot_service.loads(text).goal_monthly_krw == 0.0


@pytest.mark.parametrize("junk", [
    None, "", "   ", "not json", "[]", "null", "0", '"hello"',
    "{}", '{"v":1}', '{"v":1,"slots":"nope"}', '{"v":1,"slots":[1,2,3]}',
    '{"v":999,"slots":[]}',                       # 모르는 형식 번호
    '{"v":1,"slots":[{"name":"x"}]}',             # tactic 이 없음
    '{"v":1,"slots":[{"tactic":"문자열"}]}',
    "{" * 5000,
])
def test_loads_never_raises(junk):
    """브라우저에서 온 값은 우리가 통제 못 합니다. 못 읽으면 빈 상태여야 합니다."""
    got = slot_service.loads(junk)
    assert got.slots == [] and got.active == 0 and got.goal_monthly_krw == 0.0


def test_loads_clamps_active_into_range():
    slots = [_slot("a", ["SCHD"])]
    text = json.dumps({"v": slot_service.STORE_VERSION, "active": 99,
                       "slots": [{"name": "a", "tactic": slots[0].tactic}]})
    got = slot_service.loads(text)
    assert got.active == 0 and len(got.slots) == 1


def test_loads_caps_at_max_slots():
    many = [{"name": f"s{i}", "tactic": _slot(f"s{i}", ["SCHD"]).tactic}
            for i in range(10)]
    text = json.dumps({"v": slot_service.STORE_VERSION, "active": 0, "slots": many})
    assert len(slot_service.loads(text).slots) == slot_service.MAX_SLOTS


def test_broken_tactic_becomes_an_empty_portfolio_not_a_crash():
    """저장된 전술 하나가 깨져도 그 칸만 비면 됩니다. 앱이 죽으면 안 됩니다."""
    bad = slot_service.Slot(name="깨진 것", tactic={"positions": "이건 목록이 아님"})
    p = bad.to_portfolio()
    assert p.securities == []
    assert p.name == "깨진 것"


def test_unique_name_avoids_collisions():
    slots = [_slot("새 전술", []), _slot("새 전술 2", [])]
    assert slot_service.unique_name(slots) == "새 전술 3"
    assert slot_service.unique_name([]) == "새 전술"


# =====================================================================
# ZIP 백업
# =====================================================================
def test_zip_contains_one_json_per_slot_named_by_tactic_and_date():
    slots = [_slot("현재안", ["SCHD"]), _slot("공격안", ["JEPQ"]), _slot("은퇴안", ["TLT"])]
    names = zipfile.ZipFile(io.BytesIO(slot_service.to_zip(slots))).namelist()
    assert len(names) == 3
    today = f"{config.today_local():%Y%m%d}"
    for nm, slot in zip(sorted(names), slots):
        assert nm.endswith(".json")
        assert today in nm
    joined = " ".join(names)
    for expected in ("현재안", "공격안", "은퇴안"):
        assert expected in joined


def test_zip_filename_says_how_many():
    assert "전술3개" in slot_service.zip_filename(3)
    assert slot_service.zip_filename(3).endswith(".zip")
    assert f"{config.today_local():%Y%m%d}" in slot_service.zip_filename(3)


def test_zip_does_not_lose_a_slot_when_two_have_the_same_name():
    """같은 이름이 둘이면 파일명도 같아집니다. 푸는 쪽에서 하나가 덮어써집니다."""
    slots = [_slot("새 전술", ["SCHD"]), _slot("새 전술", ["JEPQ"])]
    names = zipfile.ZipFile(io.BytesIO(slot_service.to_zip(slots))).namelist()
    assert len(set(names)) == 2


def test_zip_round_trip_restores_every_slot():
    slots = [_slot("현재안", ["SCHD", "JEPQ"]), _slot("공격안", ["QQQI"])]
    res = slot_service.read_upload("backup.zip", slot_service.to_zip(slots))
    assert res.ok and res.replace_all
    assert len(res.slots) == 2
    restored = sorted([x.ticker for s in res.slots for x in s.to_portfolio().securities])
    assert restored == ["JEPQ", "QQQI", "SCHD"]


def test_zip_round_trip_keeps_slot_names():
    slots = [_slot("현재안", ["SCHD"]), _slot("은퇴안", ["TLT"])]
    res = slot_service.read_upload("backup.zip", slot_service.to_zip(slots))
    assert sorted(s.name for s in res.slots) == ["은퇴안", "현재안"]


def test_single_json_upload_replaces_only_the_current_slot():
    text = tactic_service.to_json(_portfolio("남이 준 전술", ["VOO"]))
    res = slot_service.read_upload("tactic.json", text.encode("utf-8"))
    assert res.ok and not res.replace_all and len(res.slots) == 1
    assert res.slots[0].name == "남이 준 전술"


def test_upload_rejects_a_broken_zip_without_crashing():
    res = slot_service.read_upload("x.zip", b"this is not a zip file at all")
    assert not res.ok and "ZIP" in res.message


def test_upload_rejects_a_zip_with_no_tactics():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", "hello")
    res = slot_service.read_upload("x.zip", buf.getvalue())
    assert not res.ok


def test_zip_with_one_broken_tactic_still_restores_the_others():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a.json", tactic_service.to_json(_portfolio("좋은 것", ["SCHD"])))
        zf.writestr("b.json", "{ 깨진 파일")
    res = slot_service.read_upload("x.zip", buf.getvalue())
    assert res.ok and len(res.slots) == 1
    assert res.slots[0].name == "좋은 것"


def test_zip_beyond_max_slots_says_what_it_skipped():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for i in range(5):
            zf.writestr(f"{i}.json", tactic_service.to_json(_portfolio(f"t{i}", ["SCHD"])))
    res = slot_service.read_upload("x.zip", buf.getvalue())
    assert res.ok and len(res.slots) == slot_service.MAX_SLOTS
    assert "건너뛰" in res.message


# =====================================================================
# 화면 — 저장소가 없어도(=컴포넌트가 None) 다 돌아야 한다
# =====================================================================
def _market(market):
    market.set_fx(rate=1_400.0)
    market.set_us({t: {"currency": "USD", "latest": 100.0}
                   for t in ("SCHD", "JEPQ", "QQQI", "TLT", "VOO", "O")}
                  | {i.ticker: {"currency": "USD", "latest": 100.0}
                     for p in presets.PRESETS for i in p.items if i.market == "US"})
    market.set_kr({i.ticker: {"currency": "KRW", "latest": 10_000.0}
                   for p in presets.PRESETS for i in p.items if i.market == "KR"})


def _slot_buttons(at):
    return [b for b in at.button if b.key and b.key.startswith("slot_")
            and b.key != "slot_add"]


def test_app_starts_with_one_slot_when_nothing_is_stored(market):
    """AppTest 에는 브라우저가 없어서 컴포넌트가 None 을 돌려줍니다.
    = 저장소를 못 쓰는 환경. 그래도 앱은 멀쩡해야 합니다."""
    _market(market)
    at = AppTest.from_file(APP_PATH, default_timeout=60).run()
    assert not at.exception
    assert len(at.session_state["slots"]) == 1
    assert at.session_state["slot_active"] == 0
    assert len(_slot_buttons(at)) == 1


def test_adding_a_slot_moves_there_and_leaves_the_first_one_alone(market):
    _market(market)
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["portfolio"] = _portfolio("현재안", ["SCHD", "JEPQ"])
    at.run()

    [b for b in at.button if b.key == "slot_add"][0].click().run()
    assert not at.exception
    assert len(at.session_state["slots"]) == 2
    assert at.session_state["slot_active"] == 1
    # 새 칸은 비어 있고
    assert at.session_state["portfolio"].securities == []
    # 먼저 있던 칸은 그대로 남아 있어야 합니다
    assert at.session_state["slots"][0].security_count == 2


def test_switching_back_restores_that_slots_holdings(market):
    _market(market)
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["portfolio"] = _portfolio("현재안", ["SCHD", "JEPQ"])
    at.run()
    [b for b in at.button if b.key == "slot_add"][0].click().run()

    # 새 칸에 종목을 하나 담고
    at.session_state["portfolio"] = _portfolio("공격안", ["QQQI"])
    at.run()
    # 첫 칸으로 돌아가면
    [b for b in at.button if b.key == "slot_0"][0].click().run()
    assert not at.exception
    assert at.session_state["slot_active"] == 0
    assert [s.ticker for s in at.session_state["portfolio"].securities] == ["SCHD", "JEPQ"]
    # 두 번째 칸도 그대로 살아 있어야 합니다
    assert at.session_state["slots"][1].security_count == 1


def test_empty_slot_is_swept_away_when_you_leave_it(market):
    """＋ 를 눌러보다 만 빈 칸이 탭으로 영영 남으면 안 됩니다."""
    _market(market)
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["portfolio"] = _portfolio("현재안", ["SCHD"])
    at.run()
    [b for b in at.button if b.key == "slot_add"][0].click().run()
    assert len(at.session_state["slots"]) == 2      # 빈 칸이 생겼다가

    [b for b in at.button if b.key == "slot_0"][0].click().run()
    assert not at.exception
    assert len(at.session_state["slots"]) == 1      # 떠나는 순간 치워짐
    assert at.session_state["slot_active"] == 0
    assert [s.ticker for s in at.session_state["portfolio"].securities] == ["SCHD"]


def test_the_last_slot_is_never_swept_away(market):
    """칸이 하나뿐이면 비어 있어도 남겨야 합니다. 안 그러면 갈 곳이 없어집니다."""
    _market(market)
    at = AppTest.from_file(APP_PATH, default_timeout=60).run()
    assert at.session_state["portfolio"].securities == []
    [b for b in at.button if b.key == "slot_0"][0].click().run()
    assert not at.exception
    assert len(at.session_state["slots"]) == 1


def test_adding_from_an_empty_slot_actually_adds(market):
    """빈 칸에서 ＋ 를 누르면 '하나 지우고 하나 만들기'가 되어 아무 일도 안 일어난
    것처럼 보이던 버그가 있었습니다."""
    _market(market)
    at = AppTest.from_file(APP_PATH, default_timeout=60).run()
    assert at.session_state["portfolio"].securities == []
    [b for b in at.button if b.key == "slot_add"][0].click().run()
    assert not at.exception
    assert len(at.session_state["slots"]) == 2


def _name_box(at):
    return [t for t in at.text_input if t.label == "전술명"][0]


def test_slot_button_follows_the_tactic_name_immediately(market):
    """이름을 고치면 슬롯 탭 글자도 같은 화면에서 바뀌어야 합니다.

    그래서 슬롯 바는 전술명 입력칸보다 **나중에** 그립니다(화면에서는 위에 있지만
    코드로는 뒤). 먼저 그리면 탭 이름이 한 박자 늦게 따라옵니다.
    """
    _market(market)
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["portfolio"] = _portfolio("현재안", ["SCHD"])
    at.run()
    _name_box(at).set_value("은퇴 계획").run()
    assert not at.exception
    assert _slot_buttons(at)[0].label.startswith("은퇴 계획")


@pytest.mark.parametrize("name,count,expected", [
    ("현재안", 5, "현재안 (5)"),
    ("", 0, "새 전술 (0)"),
    ("   ", 0, "새 전술 (0)"),
    # 그냥 자르면 "월 100만원 · " 에서 끊겨 뒤의 구분점과 겹쳐 고장난 것처럼 보였습니다.
    ("월 100만원 · 1억 예시", 9, "월 100만원… (9)"),
    ("아주아주아주아주긴전술이름입니다", 3, "아주아주아주아주긴전… (3)"),
])
def test_slot_label_never_ends_in_a_dangling_separator(name, count, expected):
    assert slot_service.slot_label(name, count) == expected


def test_slot_label_stays_short_enough_for_the_button():
    long_name = "가" * 100
    assert len(slot_service.slot_label(long_name, 26)) <= slot_service.SLOT_LABEL_MAX + 7


def test_tactic_name_box_shows_the_new_name_after_loading_a_preset(market):
    """전술명 입력칸에 key 를 붙였다가 실제로 겪은 버그의 회귀 테스트.

    key 가 붙은 text_input 은 예시를 불러와도 **입력칸 글자가 안 바뀝니다**
    (브라우저가 들고 있던 옛 값을 계속 돌려줌). 그러면 다음 클릭 때 옛 이름이
    되돌아와 슬롯 이름까지 덮어씁니다. key 없이 value= 로만 그려야 합니다.
    """
    _market(market)
    at = AppTest.from_file(APP_PATH, default_timeout=60).run()
    assert _name_box(at).value == "새 전술"

    [b for b in at.button if b.label.startswith("월 100만원")][0].click().run()
    assert not at.exception
    assert at.session_state["portfolio"].name == "월 100만원 · 1억 예시"
    assert _name_box(at).value == "월 100만원 · 1억 예시", "입력칸이 옛 이름에 머물러 있습니다"


def test_slot_keeps_its_name_when_another_slot_is_added(market):
    """브라우저에서 실제로 난 버그: 예시를 불러온 뒤 ＋ 를 누르면 먼저 있던 칸의
    이름이 '새 전술' 로 되돌아갔습니다."""
    _market(market)
    at = AppTest.from_file(APP_PATH, default_timeout=60).run()
    [b for b in at.button if b.label.startswith("월 100만원")][0].click().run()
    assert at.session_state["slots"][0].name == "월 100만원 · 1억 예시"

    [b for b in at.button if b.key == "slot_add"][0].click().run()
    assert not at.exception
    assert at.session_state["slots"][0].name == "월 100만원 · 1억 예시"
    assert at.session_state["slots"][0].security_count == 9


def test_cannot_exceed_max_slots(market):
    _market(market)
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["portfolio"] = _portfolio("현재안", ["SCHD"])
    at.run()
    for i in range(slot_service.MAX_SLOTS - 1):
        at.session_state["portfolio"] = _portfolio(f"t{i}", ["JEPQ"])
        at.run()
        [b for b in at.button if b.key == "slot_add"][0].click().run()
    assert len(at.session_state["slots"]) == slot_service.MAX_SLOTS
    # 다 찼으면 ＋ 버튼 자체가 없어야 합니다
    assert not [b for b in at.button if b.key == "slot_add"]


def test_switching_slots_drops_the_backtest_result(market):
    """다른 전술로 갈아탔는데 예전 백테스트 결과가 남아 있으면 그게 이 전술 것인 줄 압니다."""
    _market(market)
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["portfolio"] = _portfolio("현재안", ["SCHD"])
    at.run()
    at.session_state["bt_result"] = "가짜 결과"
    [b for b in at.button if b.key == "slot_add"][0].click().run()
    assert not at.exception
    assert "bt_result" not in at.session_state
