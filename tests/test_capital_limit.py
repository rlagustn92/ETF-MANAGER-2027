"""Portfolio.clamp_weight_pct / remaining_weight_budget_pct 테스트 (사용자 요청).

기본값(strict_capital_limit=True)에서는 종목 목표비중 편집 시 다른 종목들과의 합계가
100%(초기자본)를 넘지 않도록 자동으로 잘라내야 합니다. 토글로 끄면(False) 제한 없이
0~100% 범위로만 자릅니다(기존 동작).
"""

import pytest

import config
from models.portfolio import Portfolio
from models.security import Security
from services import tactic_service


def _portfolio_with_two(w1=0.5, w2=0.0) -> tuple[Portfolio, Security, Security]:
    p = Portfolio(name="t", initial_capital_krw=10_000_000)
    p.add(Security(market="US", ticker="A", target_weight=w1))
    p.add(Security(market="US", ticker="B", target_weight=w2))
    a, b = p.securities
    return p, a, b


def test_strict_mode_is_default_on():
    p = Portfolio(name="t", initial_capital_krw=10_000_000)
    assert p.strict_capital_limit is True
    assert config.STRICT_CAPITAL_LIMIT_DEFAULT is True


def test_remaining_budget_excludes_target_security():
    p, a, b = _portfolio_with_two(w1=0.5, w2=0.2)
    # B 를 제외하면 A(50%) 만 남음 -> B 의 여유는 50%
    assert p.remaining_weight_budget_pct(exclude_id=b.id) == pytest.approx(50.0)
    # A 를 제외하면 B(20%) 만 남음 -> A 의 여유는 80%
    assert p.remaining_weight_budget_pct(exclude_id=a.id) == pytest.approx(80.0)


def test_clamp_blocks_exceeding_100_percent_by_default():
    p, a, b = _portfolio_with_two(w1=0.7, w2=0.0)
    # A 가 이미 70% 를 쓰고 있으므로 B 는 최대 30% 까지만 가능
    clamped, was_clamped = p.clamp_weight_pct(b.id, 50.0)
    assert was_clamped is True
    assert clamped == pytest.approx(30.0)


def test_clamp_allows_within_budget_without_clamping():
    p, a, b = _portfolio_with_two(w1=0.7, w2=0.0)
    clamped, was_clamped = p.clamp_weight_pct(b.id, 20.0)
    assert was_clamped is False
    assert clamped == pytest.approx(20.0)


def test_clamp_editing_own_current_weight_does_not_self_block():
    # A 의 현재 비중(70%) 자체는 "다른 종목" 합계에서 제외되므로, A 를 70%로 "그대로" 두는
    # 편집은 잘리지 않아야 한다 (자기 자신을 이중으로 빼는 버그 방지).
    p, a, b = _portfolio_with_two(w1=0.7, w2=0.0)
    clamped, was_clamped = p.clamp_weight_pct(a.id, 70.0)
    assert was_clamped is False
    assert clamped == pytest.approx(70.0)


def test_toggle_off_allows_exceeding_100_percent():
    p, a, b = _portfolio_with_two(w1=0.7, w2=0.0)
    p.strict_capital_limit = False
    clamped, was_clamped = p.clamp_weight_pct(b.id, 90.0)
    assert was_clamped is False
    assert clamped == pytest.approx(90.0)   # 합계 160% 가 되어도 그대로 허용


def test_requesting_more_than_the_whole_seed_reports_clamping():
    """시드 전체(100%)보다 큰 값을 요청하면 조용히 줄이지 말고 "잘렸다"고 알려야 한다.

    슬라이더는 최대가 100% 라 이 경우가 없지만, '얼마어치 살까?' 금액 칸에는 시드보다
    큰 금액을 그냥 적을 수 있어서(예: 시드 1억인데 2억) 경고 없이 반토막 나면 안 된다.
    """
    p, a, b = _portfolio_with_two(w1=0.0, w2=0.0)
    clamped, was_clamped = p.clamp_weight_pct(a.id, 200.0)
    assert clamped == pytest.approx(100.0)
    assert was_clamped is True

    # 초과 허용 토글을 켠 경우에도 100% 가 상한이므로 알려준다
    p.strict_capital_limit = False
    clamped2, was_clamped2 = p.clamp_weight_pct(a.id, 200.0)
    assert clamped2 == pytest.approx(100.0)
    assert was_clamped2 is True


def test_toggle_off_still_clamps_to_0_100_range():
    p, a, b = _portfolio_with_two(w1=0.0, w2=0.0)
    p.strict_capital_limit = False
    clamped, _ = p.clamp_weight_pct(a.id, 150.0)
    assert clamped == pytest.approx(100.0)
    clamped2, _ = p.clamp_weight_pct(a.id, -10.0)
    assert clamped2 == pytest.approx(0.0)


def test_strict_capital_limit_roundtrips_through_json():
    p = Portfolio(name="t", initial_capital_krw=10_000_000, strict_capital_limit=False)
    d = p.to_dict()
    assert d["strict_capital_limit"] is False

    res = tactic_service.from_json(tactic_service.to_json(p))
    assert res.ok is True
    assert res.portfolio.strict_capital_limit is False


def test_strict_capital_limit_defaults_true_on_legacy_load():
    res = tactic_service.from_json('{"positions": []}')
    assert res.ok is True
    assert res.portfolio.strict_capital_limit is True
