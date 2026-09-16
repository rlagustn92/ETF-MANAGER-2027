"""2026-09-15 버그 점검에서 찾은 것들의 회귀 테스트.

원본 목록은 `docs/BUG_REPORT_2026-09-15.md` 입니다. 여기서 지키는 것은 하나로 요약됩니다.

    **바깥에서 들어온 값 하나 때문에 앱 화면이 죽어서는 안 된다.**

전술 JSON 은 사람들이 서로 주고받는 파일입니다. 한 사람의 깨진 파일이 그걸 연
모든 사람의 화면을 죽이면, 공유를 권할수록 손해가 됩니다. 그래서 방어를 세 겹으로
두고(모델 / 서비스 / 계산), 각 겹을 따로 테스트합니다.
"""

from __future__ import annotations

import json
import math
import pathlib

import pytest
from streamlit.testing.v1 import AppTest

import presets
from data.providers.base import FxQuote
from models import numbers
from models.portfolio import Portfolio
from models.security import MAX_TARGET_WEIGHT, Security
from services import calculation_service as calc
from services import fx_service, tactic_service

APP_PATH = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")


def _tactic(weight, capital=10_000_000, **extra) -> str:
    """종목 하나짜리 전술 파일 문자열. weight 자리에 무엇이든 넣어볼 수 있습니다."""
    position = {"market": "US", "ticker": "SCHD", "name": "Schwab US Dividend",
                "currency": "USD", "target_weight": weight}
    position.update(extra)
    return json.dumps({"app_year": 2027, "name": "t",
                       "initial_capital_krw": capital,
                       "positions": [position]})


# =====================================================================
# 공용 안전장치 (models/numbers.py)
# =====================================================================
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"),
                                 "많이", None, "", [], {}, True, False])
def test_is_finite_number_rejects_junk(bad):
    assert not numbers.is_finite_number(bad)


@pytest.mark.parametrize("good", [0, 1, -3, 0.25, "0.3", "12"])
def test_is_finite_number_accepts_real_numbers(good):
    """숫자로 적힌 문자열은 통과시킵니다. 손으로 만든 전술 파일에 실제로 있습니다."""
    assert numbers.is_finite_number(good)


def test_safe_float_never_raises():
    assert numbers.safe_float("많이") == 0.0
    assert numbers.safe_float(float("nan"), default=5.0) == 5.0
    assert numbers.safe_float(float("inf"), default=5.0) == 5.0
    assert numbers.safe_float(-3, minimum=0.0) == 0.0
    assert numbers.safe_float(999, maximum=100.0) == 100.0
    assert numbers.safe_float("0.3") == 0.3


def test_safe_float_does_not_treat_true_as_one():
    """`"target_weight": true` 가 조용히 100% 가 되면 안 됩니다."""
    assert numbers.safe_float(True) == 0.0


# =====================================================================
# 버그 1·2 — NaN / 무한대 / 문자열 비중
# =====================================================================
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), "많이", True, None])
def test_broken_weight_loads_as_zero_instead_of_crashing(bad):
    res = tactic_service.from_json(_tactic(bad))
    assert res.ok, res.message
    assert res.portfolio.securities[0].target_weight == 0.0


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), "많이"])
def test_broken_weight_tells_the_user_what_happened(bad):
    """조용히 고치면 사용자는 '내 비중이 왜 0 이지?' 를 영영 모릅니다."""
    res = tactic_service.from_json(_tactic(bad))
    assert "비중" in res.message


def test_numeric_string_weight_still_works():
    """예전 파일에 있는 "0.3" 까지 거절하면 멀쩡한 전술이 안 열립니다."""
    res = tactic_service.from_json(_tactic("0.3"))
    assert res.ok
    assert res.portfolio.securities[0].target_weight == pytest.approx(0.3)
    assert "비중" not in res.message


def test_negative_weight_becomes_zero_with_notice():
    res = tactic_service.from_json(_tactic(-0.5))
    assert res.ok
    assert res.portfolio.securities[0].target_weight == 0.0
    assert "음수" in res.message


def test_absurdly_large_weight_is_capped_so_math_stays_finite():
    """1e300 을 그대로 두면 '시드 x 비중' 이 무한대가 되고 math.floor 에서 죽습니다."""
    sec = Security(market="US", ticker="SCHD", target_weight=1e300)
    assert sec.target_weight == MAX_TARGET_WEIGHT
    amount = calc.calculate_target_amount(10_000_000, sec.target_weight)
    assert math.isfinite(amount)
    assert math.isfinite(calc.calculate_integer_shares(amount, 1_000.0))


def test_broken_manual_inputs_are_emptied_not_zeroed():
    """0 으로 바꾸면 '분배금 0원짜리 종목' 이 되어 조용히 틀립니다. 비워야 자동 조회를 씁니다."""
    res = tactic_service.from_json(
        _tactic(0.3, manual_ttm_per_share=float("nan"), manual_price="비쌈"))
    assert res.ok
    sec = res.portfolio.securities[0]
    assert sec.manual_ttm_per_share is None
    assert sec.manual_price is None
    assert "자동 조회" in res.message


def test_broken_coordinates_land_in_the_middle():
    """NaN 을 그냥 두면 min(1.0, nan) 이 1.0 을 돌려줘서 종목이 슬그머니 구석에 붙습니다."""
    sec = Security(market="US", ticker="SCHD", visual_x=float("nan"), visual_y=float("inf"))
    assert sec.visual_x == 0.5 and sec.visual_y == 0.5


# =====================================================================
# 버그 12 — 음수 시드
# =====================================================================
def test_negative_seed_becomes_zero_with_notice():
    res = tactic_service.from_json(_tactic(0.3, capital=-100))
    assert res.ok
    assert res.portfolio.initial_capital_krw == 0.0
    assert "시드" in res.message


def test_non_numeric_seed_is_still_rejected():
    """'숫자가 아닌 시드' 는 예전처럼 분명히 거절합니다. 뜻을 짐작할 수 없으니까요."""
    res = tactic_service.from_json(_tactic(0.3, capital="많이"))
    assert not res.ok
    assert "initial_capital_krw" in res.message


def test_clean_file_produces_no_noise():
    res = tactic_service.from_json(_tactic(0.3))
    assert res.ok and res.message == ""


# =====================================================================
# 윈도우에서 저장한 전술 파일 (BOM)
# =====================================================================
def test_file_saved_by_notepad_or_excel_still_opens():
    """메모장·엑셀·PowerShell 로 저장하면 파일 앞에 안 보이는 BOM 이 붙습니다.

    "utf-8" 로 읽으면 그 BOM 이 첫 글자가 되어 JSON 파서가 통째로 거절하고,
    사용자에게는 **"내가 방금 저장한 내 전술을 앱이 안 열어준다"** 로 보입니다.
    윈도우 사용자가 전술 파일을 손으로 고치면 거의 항상 이렇게 됩니다.
    """
    raw = _tactic(0.3).encode("utf-8-sig")
    assert raw.startswith(b"\xef\xbb\xbf")     # 진짜 BOM 이 붙어 있는지부터 확인
    res = tactic_service.from_json(raw)
    assert res.ok, res.message
    assert res.portfolio.securities[0].target_weight == pytest.approx(0.3)


def test_plain_utf8_file_still_opens():
    res = tactic_service.from_json(_tactic(0.3).encode("utf-8"))
    assert res.ok and res.portfolio.securities[0].ticker == "SCHD"


# =====================================================================
# 버그 3 — 환율이 0 / 음수 / NaN
# =====================================================================
@pytest.mark.parametrize("bad", [0, -1200, float("nan"), float("inf"), None])
def test_bad_fx_rate_is_treated_as_unavailable(monkeypatch, bad):
    """조회 실패 경로는 이미 잘 돕니다. 이상한 값도 그 길로 보내면 화면이 삽니다."""
    from datetime import date as _date

    monkeypatch.setattr(
        fx_service.fx_provider, "get_latest_rate",
        lambda: FxQuote(pair="USD/KRW", rate=bad, as_of=_date(2026, 9, 10), source="fake"))
    out = fx_service.current_usdkrw()
    assert not out.ok
    assert out.rate is None
    assert "환율" in out.message


def test_good_fx_rate_still_passes(monkeypatch):
    from datetime import date as _date

    monkeypatch.setattr(
        fx_service.fx_provider, "get_latest_rate",
        lambda: FxQuote(pair="USD/KRW", rate=1380.5, as_of=_date(2026, 9, 10), source="fake"))
    out = fx_service.current_usdkrw()
    assert out.ok and out.rate == pytest.approx(1380.5)


# =====================================================================
# 계산 함수 — 마지막 방어선 (시세 API 가 NaN 을 줄 수 있습니다)
# =====================================================================
def test_nan_price_is_treated_as_missing_price():
    """NaN <= 0 은 False 라, 안 막으면 math.floor(nan) 까지 흘러가 앱이 죽습니다."""
    with pytest.raises(ValueError):
        calc.calculate_integer_shares(1_000_000, float("nan"))
    with pytest.raises(ValueError):
        calc.calculate_fractional_shares(1_000_000, float("nan"))


def test_nan_amount_buys_nothing():
    assert calc.calculate_integer_shares(float("nan"), 1_000.0) == 0
    assert calc.calculate_fractional_shares(float("nan"), 1_000.0) == 0.0


def test_nan_inputs_do_not_crash_the_other_formulas():
    assert calc.calculate_actual_investment(float("nan"), 100.0) == 0.0
    assert calc.calculate_annual_distribution(10, float("nan")) == 0.0
    assert calc.calculate_target_amount(float("nan"), 0.3) == 0.0


def test_to_krw_rejects_nan_rate():
    with pytest.raises(ValueError):
        calc.to_krw(500, float("nan"))


# =====================================================================
# 화면 수준 — 실제로 안 죽는지
# =====================================================================
def _market_for_presets(market):
    market.set_fx(rate=1_400.0)
    market.set_us({i.ticker: {"currency": "USD", "latest": 100.0}
                   for p in presets.PRESETS for i in p.items if i.market == "US"})
    market.set_kr({i.ticker: {"currency": "KRW", "latest": 10_000.0}
                   for p in presets.PRESETS for i in p.items if i.market == "KR"})
    market.set_us({**{i.ticker: {"currency": "USD", "latest": 100.0}
                      for p in presets.PRESETS for i in p.items if i.market == "US"},
                   "SCHD": {"currency": "USD", "latest": 30.0}})


def test_app_survives_a_broken_tactic_file(market):
    """이게 이 파일의 핵심입니다. 깨진 전술을 열어도 화면이 살아 있어야 합니다."""
    _market_for_presets(market)
    res = tactic_service.from_json(_tactic(float("nan")))
    assert res.ok

    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["portfolio"] = res.portfolio
    at.run()
    assert not at.exception


def test_app_survives_a_string_weight(market):
    _market_for_presets(market)
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["portfolio"] = tactic_service.from_json(_tactic("많이")).portfolio
    at.run()
    assert not at.exception


# =====================================================================
# 버그 7 — 확인창이 안 사라진다
# =====================================================================
def test_preset_confirm_closes_when_the_user_does_something_else(market):
    """확인창을 띄워둔 채 다른 종목을 고르면 창이 닫혀야 합니다.

    안 닫히면 경고가 계속 방해하고, 실수로 '네, 바꿀게요' 를 누르는 순간
    작업하던 포트폴리오가 통째로 날아갑니다.
    """
    _market_for_presets(market)
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["portfolio"] = presets.build_portfolio(presets.AGGRESSIVE)
    at.session_state["preset_pending"] = presets.STABLE.key
    at.run()
    # 확인창 문구는 "지워집니다"(초기화) / "지워지고 N종목으로 바뀝니다"(예시) 두 가지입니다.
    assert any("지워" in w.value for w in at.warning)          # 확인창이 떠 있고

    target = at.session_state["portfolio"].securities[-1]
    [b for b in at.button if b.key == f"pick_{target.id}"][0].click().run()

    assert not at.exception
    assert "preset_pending" not in at.session_state          # 닫혔고
    # 확인창이 닫혔을 뿐, 담아둔 종목은 그대로여야 합니다.
    assert len(at.session_state["portfolio"].securities) == len(presets.AGGRESSIVE.items)


def test_preset_confirm_closes_when_a_security_is_removed(market):
    _market_for_presets(market)
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["portfolio"] = presets.build_portfolio(presets.AGGRESSIVE)
    at.session_state["selected_id"] = at.session_state["portfolio"].securities[0].id
    at.session_state["preset_pending"] = presets.STABLE.key
    at.run()

    [b for b in at.button if b.label.startswith("🗑")][0].click().run()
    assert not at.exception
    assert "preset_pending" not in at.session_state


# =====================================================================
# 버그 8 — 한도를 줄이면 초과 상태가 조용히 남는다
# =====================================================================
def test_shrinking_the_squad_limit_says_something(market):
    _market_for_presets(market)
    p = presets.build_portfolio(presets.AGGRESSIVE)
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["portfolio"] = p
    # 한도만 기본(11)으로 줄이고 종목은 그대로 둔 상태 = 사용자가 토글을 끈 직후
    at.session_state["squad_full_toggle"] = False
    at.run()

    assert not at.exception
    captions = " ".join(c.value for c in at.caption)
    if len(p.securities) > at.session_state["portfolio"].max_squad_size:
        assert "한도" in captions and "넘습니다" in captions


# =====================================================================
# 버그 5 — 낡은 백테스트 결과
# =====================================================================
def test_stale_backtest_is_flagged(market):
    """백테스트를 돌린 뒤 종목을 지우면 '조건이 다르다' 고 알려야 합니다."""
    _market_for_presets(market)
    from tests.conftest import daily_series

    market.set_us({"SCHD": {"currency": "USD", "latest": 30.0,
                            "history": daily_series("2020-01-01", "2026-09-10", 30.0)},
                   "JEPQ": {"currency": "USD", "latest": 60.0,
                            "history": daily_series("2020-01-01", "2026-09-10", 60.0)}})
    p = Portfolio(name="t", initial_capital_krw=10_000_000)
    p.add(Security(market="US", ticker="SCHD", currency="USD", target_weight=0.5))
    p.add(Security(market="US", ticker="JEPQ", currency="USD", target_weight=0.5))

    at = AppTest.from_file(APP_PATH, default_timeout=90)
    at.session_state["portfolio"] = p
    at.run()
    [b for b in at.button if b.label == "실행하기"][0].click().run()
    assert not at.exception
    # AppTest 의 session_state 에는 .get() 이 없습니다. in / [] 으로 봅니다.
    assert "bt_result" in at.session_state
    # 돌린 직후에는 낡지 않았습니다.
    assert not any("다른 조건" in w.value for w in at.warning)

    # 종목을 하나 지우면 같은 결과가 낡은 것이 됩니다.
    at.session_state["selected_id"] = at.session_state["portfolio"].securities[0].id
    at.run()
    [b for b in at.button if b.label.startswith("🗑")][0].click().run()
    assert not at.exception

    assert "bt_result" in at.session_state                   # 지우지는 않고
    assert any("다른 조건" in w.value for w in at.warning)     # 낡았다고 알려줍니다
    # 무엇을 돌린 것인지는 항상 붙어 있어야 합니다(캡처해서 공유할 때도 같이 나감).
    assert any("돌린 조건" in c.value for c in at.caption)


# =====================================================================
# 버그 6 — 매수 입력에 NaN 이 오면 비중이 100% 가 된다
# =====================================================================
def test_nan_from_the_buy_input_component_is_ignored(market):
    """브라우저에서 온 값은 받는 쪽에서 검사합니다.

    NaN 이 들어오면 clamp 가 `min(100, nan)` -> 100 을 돌려줘서 비중이 조용히
    100% 로 튑니다. 다른 종목 비중이 전부 눌리는데, 재현이 어려워
    "가끔 비중이 이상해진다" 는 제보로만 올 유형입니다.
    """
    market.set_fx(rate=1_400.0)
    market.set_us({"SCHD": {"currency": "USD", "latest": 30.0}})
    p = Portfolio(name="t", initial_capital_krw=10_000_000)
    p.add(Security(market="US", ticker="SCHD", currency="USD", target_weight=0.25))
    sec_id = p.securities[0].id

    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["portfolio"] = p
    at.session_state["selected_id"] = sec_id
    at.run()
    assert at.session_state[f"wsel_{sec_id}"] == pytest.approx(25.0)

    at.session_state[f"buy_{sec_id}"] = {"source": "amount", "amount": float("nan"),
                                         "qty": 0, "nonce": 12345}
    at.run()

    assert not at.exception
    assert at.session_state[f"wsel_{sec_id}"] == pytest.approx(25.0), "비중이 유지돼야 합니다"


def test_a_real_amount_from_the_component_still_applies(market):
    """방어를 넣다가 멀쩡한 입력까지 막으면 기능이 죽습니다."""
    market.set_fx(rate=1_400.0)
    market.set_us({"SCHD": {"currency": "USD", "latest": 30.0}})
    p = Portfolio(name="t", initial_capital_krw=10_000_000)
    p.add(Security(market="US", ticker="SCHD", currency="USD", target_weight=0.25))
    sec_id = p.securities[0].id

    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["portfolio"] = p
    at.session_state["selected_id"] = sec_id
    at.run()

    at.session_state[f"buy_{sec_id}"] = {"source": "amount", "amount": 4_000_000.0,
                                         "qty": 0, "nonce": 999}
    at.run()

    assert not at.exception
    assert at.session_state[f"wsel_{sec_id}"] == pytest.approx(40.0)
