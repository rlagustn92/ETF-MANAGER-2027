"""숫자 표기 테스트 (formatting.py).

돈을 잘못 적으면 사용자가 그대로 오해합니다. 특히 won_short 는 캡처 이미지에
찍혀 커뮤니티로 퍼지므로, 틀린 숫자가 박제됩니다. 경계값을 못 박아 둡니다.
"""

from __future__ import annotations

import pytest

import config
from formatting import native_amt, pct, won, won_short


# ---------------------------------------------------------------- won_short
@pytest.mark.parametrize("value,expected", [
    (0, "0원"),
    (1, "1원"),
    (9_999, "9,999원"),
    (10_000, "1.0만"),
    (99_999, "10.0만"),
    (187_000, "18.7만"),          # 월 분배금이 흔히 이 구간입니다
    (999_999, "100.0만"),
    (1_000_000, "100만"),
    (9_999_999, "1,000만"),
    (45_000_000, "4,500만"),
    (99_999_999, "10,000만"),
    (100_000_000, "1억"),         # "1.00억" 이 아니라 "1억"
    (120_000_000, "1.2억"),
    (123_400_000, "1.23억"),
    (1_000_000_000, "10억"),      # rstrip("0") 이 "10" 의 0 을 먹으면 안 됨
    (10_000_000_000, "100억"),
    (1_000_000_000_000, "10,000억"),
])
def test_won_short_boundaries(value, expected):
    assert won_short(value) == expected


@pytest.mark.parametrize("value,expected", [
    (-45_000_000, "-4,500만"),
    (-187_000, "-18.7만"),
    (-500, "-500원"),
    (-100_000_000, "-1억"),
])
def test_won_short_keeps_the_minus_sign(value, expected):
    """잔여현금은 음수가 될 수 있습니다. 부호가 사라지면 정반대로 읽힙니다."""
    assert won_short(value) == expected


def test_won_short_none_is_not_zero():
    """데이터가 없는 것과 0원은 완전히 다른 뜻입니다."""
    assert won_short(None) == config.NO_DATA_TEXT
    assert won_short(0) == "0원"


def test_won_short_sub_one_won_does_not_show_decimals():
    assert won_short(0.4) == "0원"


def test_won_short_is_always_shorter_than_won():
    """짧게 쓰려고 만든 함수이므로, 큰 금액에서 원래 표기보다 길면 의미가 없습니다."""
    for v in (45_000_000, 187_000, 1_234_567_890):
        assert len(won_short(v)) < len(won(v)), v


# ---------------------------------------------------------------- 나머지
def test_won_and_pct_and_native_amt():
    assert won(45_000_000) == "₩45,000,000"
    assert won(None) == config.NO_DATA_TEXT
    assert pct(14.345) == "14.35%"
    assert pct(None) == config.NO_DATA_TEXT
    assert native_amt(10757.4, "KRW") == "10,757"      # 원화는 소수점 없음
    assert native_amt(59.786, "USD") == "59.79"
    assert native_amt(None, "USD") == config.NO_DATA_TEXT
