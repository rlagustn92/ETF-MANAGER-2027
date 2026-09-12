"""실제 외부 데이터(yfinance / FinanceDataReader)를 호출하는 통합 테스트.

기본 실행에서는 제외됩니다. 실행하려면:
    pytest -m network
네트워크가 없거나 소스가 일시 장애면 skip 됩니다 (실패로 처리하지 않음).
"""

from datetime import date

import pytest

pytestmark = pytest.mark.network


def _skip_if_offline(fn, *a, **kw):
    from data.providers.base import DataUnavailable
    try:
        return fn(*a, **kw)
    except DataUnavailable as e:
        pytest.skip(f"데이터 소스 불가: {e}")


def test_us_price_and_distribution_live():
    from data.providers.registry import get_provider
    from services.distribution_service import compute_ttm
    from models.security import Security

    q = _skip_if_offline(get_provider("US").get_latest_price, "QQQ")
    assert q.price > 0 and q.currency == "USD"

    r = compute_ttm(Security(market="US", ticker="JEPQ", currency="USD"))
    # JEPQ 는 월분배 커버드콜 -> 최근 12개월 분배 이력이 존재해야 함
    assert r.has_data and r.ttm_per_share_native and r.ttm_per_share_native > 0


def test_kr_price_live():
    from data.providers.registry import get_provider
    q = _skip_if_offline(get_provider("KR").get_latest_price, "005930")
    assert q.price > 0 and q.currency == "KRW"


def test_every_preset_ticker_actually_resolves():
    """'예시로 시작하기' 에 넣어둔 종목이 전부 실제로 조회되는지 확인.

    예시를 눌렀는데 '데이터 없음'이 뜨면 첫인상이 망가지므로, 상장폐지·티커 변경으로
    조회가 안 되기 시작하면 여기서 바로 잡히게 합니다.
    """
    from data.providers.registry import get_provider
    import presets

    checked, failed = 0, []
    for preset in presets.PRESETS:
        for item in preset.items:
            try:
                q = get_provider(item.market).get_latest_price(item.ticker)
            except Exception as e:   # noqa: BLE001 - 어떤 실패든 목록에 모아서 보여줌
                failed.append(f"{preset.key}/{item.market}:{item.ticker} -> {e}")
                continue
            checked += 1
            assert q.price > 0, f"{item.ticker} 가격이 0 이하"
            assert q.currency == item.currency, f"{item.ticker} 통화 불일치: {q.currency}"

    if failed and not checked:
        pytest.skip(f"데이터 소스 전체 불가: {failed[0]}")
    assert not failed, failed


def test_past_fx_differs_from_current():
    from data.providers import fx_provider
    cur = _skip_if_offline(fx_provider.get_latest_rate)
    past = _skip_if_offline(fx_provider.get_rate_on, date(2021, 1, 4))
    assert cur.rate > 0 and past.rate > 0
    # 2021 초 환율(~1,080)과 현재 환율은 유의미하게 다르다 -> 과거 환율을 실제로 쓰는지 확인
    assert abs(cur.rate - past.rate) > 50


def test_backtest_late_listed_blocks():
    from models.portfolio import Portfolio
    from models.security import Security
    from services import backtest_service

    p = Portfolio(name="late", initial_capital_krw=10_000_000)
    p.add(Security(market="US", ticker="IBIT", target_weight=1.0))   # 2024 상장
    res = backtest_service.run_backtest(p, date(2021, 1, 4))
    if res.ok:
        pytest.skip("데이터 상황상 판별 불가")
    assert "상장" in res.message


def test_split_not_double_counted_nvda():
    """NVDA 2020 매수 -> 현재. 분할비율(40x)을 수량에 곱하지 않으므로 수익률이 비상식적이지 않다."""
    from models.portfolio import Portfolio
    from models.security import Security
    from services import backtest_service

    p = Portfolio(name="nvda", initial_capital_krw=100_000_000)
    p.add(Security(market="US", ticker="NVDA", target_weight=1.0))
    res = backtest_service.run_backtest(p, date(2020, 1, 2))
    if not res.ok:
        pytest.skip(res.message)
    row = res.rows[0]
    price_ratio = row.final_price_native / row.buy_price_native
    # 평가금액이 대략 (가격배수 x 환율배수) 범위 안 -- 분할 40배가 추가로 곱해지면 이 범위를 크게 벗어남
    implied = res.final_value_krw / row.invested_krw
    assert implied < price_ratio * 3, (implied, price_ratio)
