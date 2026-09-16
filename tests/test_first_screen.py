"""처음 화면 (빈 전술판 + 예시 버튼) 테스트.

여기서 지키는 것
----------------
"처음 온 사람인가?" 를 알아내려고 애쓰지 않습니다. **담은 종목이 0개인가**만 봅니다.
그래서 기억할 것도, 저장할 것도 없습니다 -- 10년 쓴 사람이 초기화를 눌러도
같은 안내가 뜨는 게 맞습니다.
"""

from __future__ import annotations

import pathlib

import pytest
from streamlit.testing.v1 import AppTest

import presets
from formatting import won_short
from models.portfolio import Portfolio
from models.security import Security

APP_PATH = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")
PITCH_HTML = (pathlib.Path(__file__).resolve().parent.parent
              / "components" / "football_pitch" / "frontend" / "index.html")


def _market(market):
    market.set_fx(rate=1_400.0)
    market.set_us({i.ticker: {"currency": "USD", "latest": 100.0}
                   for p in presets.PRESETS for i in p.items if i.market == "US"})
    market.set_kr({i.ticker: {"currency": "KRW", "latest": 10_000.0}
                   for p in presets.PRESETS for i in p.items if i.market == "KR"})


# =====================================================================
# 예시 버튼 -- 누르기 전에 뭘 받는지 보이는가
# =====================================================================
@pytest.mark.parametrize("preset", presets.PRESETS)
def test_every_preset_says_how_many_and_what_seed(preset):
    chip = preset.chip()
    assert f"{len(preset.items)}종목" in chip
    assert won_short(preset.capital_krw) in chip


def test_reset_chip_says_it_empties_things():
    assert "비웁니다" in presets.RESET.chip()


def test_chip_does_not_promise_a_monthly_amount():
    """월 분배금은 시세로 계산해야 나옵니다. 코드에 박아두면 **반드시 낡습니다.**

    낡은 금액을 버튼에 적어두느니 안 적는 게 낫습니다.
    """
    for preset in presets.PRESETS:
        assert "월 " not in preset.chip()


def test_the_screen_shows_the_chip_under_each_preset_button(market):
    _market(market)
    at = AppTest.from_file(APP_PATH, default_timeout=60).run()
    captions = " ".join(c.value for c in at.caption)
    for preset in presets.PRESETS:
        assert preset.chip() in captions


# =====================================================================
# 확인창 -- 무엇이 들어오는지, 시드가 바뀌는지
# =====================================================================
def _warnings(at):
    return " ".join(w.value for w in at.warning)


def test_confirm_says_what_arrives_not_just_what_goes(market):
    _market(market)
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["portfolio"] = presets.build_portfolio(presets.STABLE)
    at.run()

    [b for b in at.button if b.key == "preset_aggressive"][0].click().run()
    text = _warnings(at)
    assert "지워지고" in text
    assert f"{len(presets.AGGRESSIVE.items)}종목" in text


def test_confirm_warns_when_the_seed_will_change(market):
    """예시를 누르면 내 시드까지 바뀝니다. 누르고 나서 알면 늦습니다."""
    _market(market)
    p = presets.build_portfolio(presets.STABLE)
    p.initial_capital_krw = 30_000_000
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["portfolio"] = p
    at.run()

    [b for b in at.button if b.key == "preset_income50_5000"][0].click().run()
    text = _warnings(at)
    assert "시드도" in text
    assert won_short(50_000_000) in text


def test_confirm_stays_quiet_about_the_seed_when_it_does_not_change(market):
    _market(market)
    p = presets.build_portfolio(presets.STABLE)      # 시드 1억
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["portfolio"] = p
    at.run()

    [b for b in at.button if b.key == "preset_balanced"][0].click().run()   # 역시 1억
    assert "시드도" not in _warnings(at)


# =====================================================================
# 빈 전술판 -- 안내가 상태에서 나오는가
# =====================================================================
def test_pitch_has_an_empty_state_message():
    """텅 빈 초록 화면은 "고장난 건가?" 로 읽힙니다."""
    html = PITCH_HTML.read_text(encoding="utf-8")
    assert 'id="empty"' in html
    assert "여기에 종목을 올리면 전술이 됩니다" in html


def test_pitch_swaps_the_bottom_hint_when_there_is_nothing_to_drag():
    """카드가 없는데 "카드를 잡아 끌어놓으세요" 라고 하면 끌 게 없습니다."""
    html = PITCH_HTML.read_text(encoding="utf-8")
    assert "HINT_EMPTY" in html and "HINT_DRAG" in html
    assert "players.length === 0" in html


def test_empty_state_is_decided_by_the_state_not_by_remembering_the_person(market):
    """'처음 온 사람인지' 를 기억해두는 값이 없어야 합니다.

    기억하기 시작하면 저장할 것이 생기고, 초기화한 사람에게는 안내가 영영 안 뜹니다.
    """
    _market(market)
    at = AppTest.from_file(APP_PATH, default_timeout=60).run()
    assert not at.exception
    keys = list(at.session_state.filtered_state)
    assert not [k for k in keys if "onboard" in k or "tutorial" in k or "first_visit" in k]


def test_the_guidance_comes_back_after_you_empty_the_portfolio(market):
    """10년 쓴 사람도 초기화하면 할 일이 없는 상태입니다. 그때 안내가 뜨는 게 맞습니다."""
    _market(market)
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["portfolio"] = presets.build_portfolio(presets.STABLE)
    at.run()

    [b for b in at.button if b.key == "preset_reset"][0].click().run()
    [b for b in at.button if b.key == "preset_ok"][0].click().run()
    assert not at.exception
    assert at.session_state["portfolio"].securities == []
    # 전술판 컴포넌트가 "종목 0개" 상태로 그려지면 안내는 그쪽에서 나옵니다.
    # 여기서는 앱이 그 상태를 제대로 만들어 주는지까지만 봅니다.
    assert "아래에서 검색해 종목을 추가하세요." in " ".join(c.value for c in at.caption)
