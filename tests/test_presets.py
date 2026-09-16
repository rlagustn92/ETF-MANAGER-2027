"""예시 포트폴리오('예시로 시작하기') 테스트.

여기서 지키려는 것:
- 비중 합계가 정확히 100% (예시를 불러왔는데 시드가 남거나 초과하면 안 됨)
- 한 예시 안에 같은 종목이 두 번 들어가지 않음
- 불러오면 시드가 1억으로 고정되고, 모든 종목이 전술판 슬롯에 배치됨
- 버튼을 누르면 실제로 화면의 전술이 교체됨 (AppTest)

종목이 실제로 조회되는지(가격/분배금)는 네트워크가 필요하므로 test_network 쪽에서
확인합니다. 여기서는 네트워크 없이 구성 자체의 정합성만 봅니다.
"""

from __future__ import annotations

import pathlib

import pytest
from streamlit.testing.v1 import AppTest

import presets
from models.portfolio import Portfolio

APP_PATH = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")


def test_presets_have_unique_keys_and_expected_labels():
    """앞 3개는 성향별, 뒤 2개는 목표 금액별입니다 (화면에서도 두 줄로 나눠 그립니다)."""
    assert len(presets.PRESETS) == 5
    keys = [p.key for p in presets.PRESETS]
    assert len(set(keys)) == len(keys)
    labels = [p.label for p in presets.PRESETS]
    assert labels == ["안정배당형", "보통배당형", "공격배당형",
                      "월 100만원 · 1억", "월 50만원 · 5천만원"]


@pytest.mark.parametrize("preset", presets.PRESETS, ids=lambda p: p.key)
def test_weights_sum_to_exactly_100(preset):
    assert preset.total_weight_pct() == pytest.approx(100.0)


@pytest.mark.parametrize("preset", presets.PRESETS, ids=lambda p: p.key)
def test_no_duplicate_tickers_within_a_preset(preset):
    pairs = [(i.market, i.ticker) for i in preset.items]
    assert len(set(pairs)) == len(pairs), pairs


@pytest.mark.parametrize("preset", presets.PRESETS, ids=lambda p: p.key)
def test_every_item_has_a_market_and_currency_we_support(preset):
    for i in preset.items:
        assert i.market in ("US", "KR")
        assert i.currency in ("USD", "KRW")
        assert (i.currency == "KRW") == (i.market == "KR")


@pytest.mark.parametrize("preset", presets.PRESETS, ids=lambda p: p.key)
def test_build_portfolio_fills_capital_weights_and_slots(preset):
    p = presets.build_portfolio(preset)

    assert isinstance(p, Portfolio)
    # 시드는 예시마다 다를 수 있습니다("월 50만원 · 5천만원" 은 5천만원).
    assert p.initial_capital_krw == preset.capital_krw
    assert len(p.securities) == len(preset.items)
    assert sum(s.target_weight for s in p.securities) == pytest.approx(1.0)
    # 전술판에 그리려면 모두 슬롯이 있어야 하고, 슬롯이 겹치면 안 된다
    slots = [s.slot for s in p.securities]
    assert all(slots), slots
    assert len(set(slots)) == len(slots), slots


def test_income_presets_use_the_seed_their_name_promises():
    """이름에 원금이 적혀 있으므로, 불러왔을 때 그 원금으로 채워져야 합니다.
    안 그러면 "월 50만원 · 5천만원" 을 눌렀는데 시드가 1억으로 뜹니다."""
    assert presets.INCOME_100_1E.capital_krw == 100_000_000
    assert presets.INCOME_50_5000.capital_krw == 50_000_000


@pytest.mark.parametrize("preset", (presets.INCOME_100_1E, presets.INCOME_50_5000),
                         ids=lambda p: p.key)
def test_income_presets_are_split_evenly_between_the_two_markets(preset):
    """한쪽 나라에 몰면 환율이 움직일 때 통째로 흔들립니다 (사용자 요청: 분산)."""
    us = sum(i.weight_pct for i in preset.items if i.market == "US")
    kr = sum(i.weight_pct for i in preset.items if i.market == "KR")
    assert us == pytest.approx(50.0), f"미국 {us}%"
    assert kr == pytest.approx(50.0), f"한국 {kr}%"


@pytest.mark.parametrize("preset", (presets.INCOME_100_1E, presets.INCOME_50_5000),
                         ids=lambda p: p.key)
def test_income_presets_do_not_lean_on_one_holding(preset):
    """한 종목이 30%를 넘으면 그 종목 하나가 분배금을 떠받치는 구조가 됩니다."""
    biggest = max(i.weight_pct for i in preset.items)
    assert biggest <= 25.0, f"최대 비중 {biggest}%"


def test_presets_fit_within_default_squad_size():
    """기본 보유 한도(11종목)를 넘으면 예시를 불러올 때 에러가 납니다."""
    import config
    for preset in presets.PRESETS:
        assert len(preset.items) <= config.SQUAD_SIZE_DEFAULT


def test_clicking_a_preset_button_replaces_the_portfolio(market):
    market.set_fx(rate=1_400.0)
    market.set_us({i.ticker: {"currency": "USD", "latest": 100.0}
                   for p in presets.PRESETS for i in p.items if i.market == "US"})
    market.set_kr({i.ticker: {"currency": "KRW", "latest": 10_000.0}
                   for p in presets.PRESETS for i in p.items if i.market == "KR"})

    at = AppTest.from_file(APP_PATH, default_timeout=60).run()
    assert not at.exception
    assert at.session_state["portfolio"].securities == []   # 처음엔 비어 있음

    stable = presets.STABLE
    [b for b in at.button if b.label == stable.label][0].click().run()
    assert not at.exception

    p = at.session_state["portfolio"]
    assert [s.ticker for s in p.securities] == [i.ticker for i in stable.items]
    assert p.initial_capital_krw == presets.PRESET_CAPITAL_KRW
    assert at.session_state["selected_id"] == p.securities[0].id


def test_preset_asks_before_wiping_existing_holdings(market):
    market.set_fx(rate=1_400.0)
    market.set_us({i.ticker: {"currency": "USD", "latest": 100.0}
                   for p in presets.PRESETS for i in p.items if i.market == "US"})
    market.set_kr({i.ticker: {"currency": "KRW", "latest": 10_000.0}
                   for p in presets.PRESETS for i in p.items if i.market == "KR"})

    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["portfolio"] = presets.build_portfolio(presets.BALANCED)
    at.run()

    # 이미 담은 게 있으면 바로 덮어쓰지 않고 확인을 받아야 한다
    [b for b in at.button if b.label == presets.AGGRESSIVE.label][0].click().run()
    assert not at.exception
    assert [s.ticker for s in at.session_state["portfolio"].securities] == \
        [i.ticker for i in presets.BALANCED.items]        # 아직 그대로
    # 예시 확인창은 "지워지고 N종목으로 바뀝니다" 라고, 들어올 것까지 같이 말합니다.
    assert any("지워지고" in w.value for w in at.warning)

    [b for b in at.button if b.label == "네, 바꿀게요"][0].click().run()
    assert not at.exception
    assert [s.ticker for s in at.session_state["portfolio"].securities] == \
        [i.ticker for i in presets.AGGRESSIVE.items]


def test_reset_button_empties_the_portfolio_after_confirming(market):
    """'초기화' 는 예시와 같은 확인 절차를 거쳐 종목을 모두 비운다 (사용자 요청)."""
    market.set_fx(rate=1_400.0)
    market.set_us({i.ticker: {"currency": "USD", "latest": 100.0}
                   for p in presets.PRESETS for i in p.items if i.market == "US"})
    market.set_kr({i.ticker: {"currency": "KRW", "latest": 10_000.0}
                   for p in presets.PRESETS for i in p.items if i.market == "KR"})

    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["portfolio"] = presets.build_portfolio(presets.STABLE)
    at.run()

    [b for b in at.button if b.label == "초기화"][0].click().run()
    assert not at.exception
    assert at.session_state["portfolio"].securities != []      # 아직 안 지워짐
    assert any("지워집니다" in w.value for w in at.warning)

    [b for b in at.button if b.label == "네, 바꿀게요"][0].click().run()
    assert not at.exception
    assert at.session_state["portfolio"].securities == []
    assert at.session_state["selected_id"] is None


def test_reset_on_empty_portfolio_does_not_crash(market):
    at = AppTest.from_file(APP_PATH, default_timeout=60).run()
    [b for b in at.button if b.label == "초기화"][0].click().run()
    assert not at.exception
    assert at.session_state["portfolio"].securities == []


def test_reset_is_not_counted_as_an_example_preset():
    assert presets.RESET not in presets.PRESETS
    assert presets.RESET in presets.ALL_BUTTONS
    assert presets.RESET.items == ()
    assert presets.get("reset") is presets.RESET


def test_yahoo_url_points_at_the_quote_page_for_us():
    assert presets.yahoo_finance_url("US", "O") == "https://finance.yahoo.com/quote/O/"
    assert presets.yahoo_finance_url("US", "SCHD") == "https://finance.yahoo.com/quote/SCHD/"


def test_yahoo_url_uses_search_for_kr_because_suffix_is_ambiguous():
    """한국 종목은 .KS/.KQ 중 무엇인지 티커만으로 알 수 없어 검색으로 보낸다."""
    url = presets.yahoo_finance_url("KR", "329200")
    assert url == "https://finance.yahoo.com/lookup/?s=329200"
    assert ".KS" not in url and ".KQ" not in url


def test_toss_url_prefixes_kr_codes_with_A():
    """토스증권 한국 종목 주소는 'A' + 종목코드 (실제 사이트에서 확인한 형식).
    영문이 섞인 코드(0219E0)도 같은 규칙입니다."""
    assert presets.toss_invest_url("KR", "329200") == "https://www.tossinvest.com/stocks/A329200"
    assert presets.toss_invest_url("KR", "0219E0") == "https://www.tossinvest.com/stocks/A0219E0"


def test_toss_url_uses_plain_ticker_for_us():
    assert presets.toss_invest_url("US", "SCHD") == "https://www.tossinvest.com/stocks/SCHD"


def test_toss_url_escapes_unexpected_characters():
    assert presets.toss_invest_url("US", "A B") == "https://www.tossinvest.com/stocks/A%20B"


def test_yahoo_url_escapes_unexpected_characters():
    assert presets.yahoo_finance_url("US", "A B&C") == "https://finance.yahoo.com/quote/A%20B%26C/"


def test_preset_cancel_keeps_current_holdings(market):
    market.set_fx(rate=1_400.0)
    market.set_us({i.ticker: {"currency": "USD", "latest": 100.0}
                   for p in presets.PRESETS for i in p.items if i.market == "US"})
    market.set_kr({i.ticker: {"currency": "KRW", "latest": 10_000.0}
                   for p in presets.PRESETS for i in p.items if i.market == "KR"})

    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["portfolio"] = presets.build_portfolio(presets.STABLE)
    at.run()

    [b for b in at.button if b.label == presets.AGGRESSIVE.label][0].click().run()
    [b for b in at.button if b.label == "취소"][0].click().run()
    assert not at.exception
    assert [s.ticker for s in at.session_state["portfolio"].securities] == \
        [i.ticker for i in presets.STABLE.items]
    assert "preset_pending" not in at.session_state
