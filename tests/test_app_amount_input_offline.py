"""app.py 의 '얼마어치 살까? / 몇 주 살까?' 입력 카드 테스트 (네트워크 없음).

이 입력칸들은 커스텀 컴포넌트(components/buy_input)입니다. 브라우저 쪽 타이핑은
여기서 재현할 수 없지만, 컴포넌트가 서버로 보내는 값은 st.session_state[buy_<id>]
로 들어오고 app.py 가 컴포넌트를 그리기 "전에" 그 값을 읽어 반영하므로, 그 값을
직접 넣어주면 실제 입력과 똑같은 경로를 검증할 수 있습니다.

검증 대상:
- 금액을 넣으면 살(BUY) 비율이 역산되고, 1주 미만은 못 사서 실제로는 덜 사는 것
- '소수점까지 사기' 를 켜면 금액을 전부 쓰는 것
- 수량을 넣으면 정확히 그 주수가 나오는 것 (반올림으로 1주 모자라지 않아야 함)
- 시드 한도를 넘으면 잘리는 것
"""

from __future__ import annotations

import pathlib

from streamlit.testing.v1 import AppTest

from models.portfolio import Portfolio
from models.security import Security

APP_PATH = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")

# 1주 = 300 USD x 환율 1,000원 = 300,000원.
# 31,000,000 / 300,000 = 103.33주 -> 정수 매수면 103주 (딱 떨어지지 않는 상황)
PRICE_USD = 300.0
FX = 1_000.0
PRICE_KRW = PRICE_USD * FX
AMOUNT = 31_000_000
CAPITAL = 100_000_000


def _run(market, *, pending=None, fractional=False, second_weight=None):
    """QQQ 한 종목(+선택적으로 시드를 차지하는 다른 종목)을 담고 앱을 실행."""
    market.set_fx(rate=FX)
    market.set_us({"A": {"currency": "USD", "latest": PRICE_USD},
                   "B": {"currency": "USD", "latest": PRICE_USD}})
    p = Portfolio(name="t", initial_capital_krw=CAPITAL, fractional_shares=fractional)
    p.add(Security(market="US", ticker="A", currency="USD", target_weight=0.0))
    if second_weight is not None:
        p.add(Security(market="US", ticker="B", currency="USD", target_weight=second_weight))
    sec_id = p.securities[0].id

    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["portfolio"] = p
    at.session_state["selected_id"] = sec_id
    if pending is not None:
        # 컴포넌트가 "사용자가 이만큼 입력했다"고 보내온 상태를 그대로 재현
        at.session_state[f"buy_{sec_id}"] = dict(pending, nonce=1)
    at.run()
    assert not at.exception
    return at


def _weight(at) -> float:
    return [s for s in at.slider if s.label == "살(BUY) 비율 (%)"][0].value


def _metrics(at) -> dict:
    return {m.label: m.value for m in at.metric}


def test_amount_input_back_calculates_weight(market):
    at = _run(market, pending={"source": "amount", "amount": AMOUNT, "qty": 0})

    assert _weight(at) == 31.0                       # 3,100만 / 1억 = 31%
    assert _metrics(at)["살(BUY) 비율"] == "31.00%"


def test_amount_buys_whole_shares_only_and_leaves_change(market):
    at = _run(market, pending={"source": "amount", "amount": AMOUNT, "qty": 0})

    expected_shares = int(AMOUNT // PRICE_KRW)       # 103주
    spent = expected_shares * PRICE_KRW              # 30,900,000
    assert _metrics(at)["보유 주식 수"] == str(expected_shares)
    assert _metrics(at)["이 종목에 들어간 돈"] == f"₩{spent:,.0f}"


def test_amount_uses_full_money_when_fractional_shares_on(market):
    at = _run(market, pending={"source": "amount", "amount": AMOUNT, "qty": 0},
              fractional=True)

    assert _weight(at) == 31.0
    # 소수점까지 살 수 있으면 금액이 그대로 다 쓰인다
    assert _metrics(at)["이 종목에 들어간 돈"] == f"₩{AMOUNT:,.0f}"


def test_quantity_input_gives_exactly_that_many_shares(market):
    """수량 -> 비중 역산 후 다시 주수를 계산해도 입력한 주수가 그대로 나와야 한다
    (반올림 때문에 1주 모자라던 버그의 회귀 테스트)."""
    at = _run(market, pending={"source": "qty", "amount": 0, "qty": 20})

    assert _metrics(at)["보유 주식 수"] == "20"
    assert _metrics(at)["이 종목에 들어간 돈"] == f"₩{20 * PRICE_KRW:,.0f}"


def test_amount_bigger_than_the_whole_seed_is_capped_with_warning(market):
    """시드(1억)보다 큰 2억을 적으면 1억까지만 반영되고, 경고가 떠야 한다."""
    at = _run(market, pending={"source": "amount", "amount": 200_000_000, "qty": 0})

    assert _weight(at) == 100.0
    warnings = [w.value for w in at.warning]
    assert any("자동 조정" in w for w in warnings), warnings


def test_amount_is_capped_by_remaining_seed_budget(market):
    """다른 종목이 이미 시드의 80% 를 쓰고 있으면 남은 20%(=2천만원)까지만 들어가야 한다."""
    at = _run(market, pending={"source": "amount", "amount": 50_000_000, "qty": 0},
              second_weight=0.80)

    assert _weight(at) == 20.0
    warnings = [w.value for w in at.warning]
    assert any("자동 조정" in w for w in warnings), warnings
