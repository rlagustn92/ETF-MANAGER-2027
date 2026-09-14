"""전술판 유니폼(이름 축약 + 브랜드 색) 테스트.

여기서 지키려는 것:
- 긴 한국 ETF 이름이 이름표 폭 안에 들어간다
- **위험 정보를 담은 단어는 잘리지 않는다** (레버리지/인버스/(H)/TR/ATM ...)
  이게 제일 중요합니다. "KODEX 코스닥150레버리지" 가 "코스닥150" 으로 줄면
  2배 상품을 일반 상품으로 오해하게 됩니다.
- 브랜드를 못 알아봐도 예외 없이 동작한다 (새로 상장한 ETF)
- 미국 종목은 티커를 그대로 쓰고 성조기 키트를 입는다
"""

from __future__ import annotations

import pytest

import pitch_kit


# ---------------------------------------------------------------- 브랜드 분리
@pytest.mark.parametrize("name,brand,rest", [
    ("TIGER 미국배당다우존스", "TIGER", "미국배당다우존스"),
    ("KODEX 200커버드콜액티브", "KODEX", "200커버드콜액티브"),
    ("SOL 미국배당다우존스(H)", "SOL", "미국배당다우존스(H)"),
    ("RISE 200고배당커버드콜ATM", "RISE", "200고배당커버드콜ATM"),
    # 리브랜딩: 옛 이름으로 들어와도 현재 브랜드로 맞춘다
    ("KBSTAR 200", "RISE", "200"),
    ("ARIRANG 고배당주", "PLUS", "고배당주"),
    ("KINDEX 미국S&P500", "ACE", "미국S&P500"),
    # 붙여 쓴 경우
    ("KODEX200", "KODEX", "200"),
    # 모르는 브랜드 -> 브랜드 없음, 이름은 그대로
    ("아무개자산 신규ETF", "", "아무개자산 신규ETF"),
    ("", "", ""),
])
def test_split_brand(name, brand, rest):
    assert pitch_kit.split_brand(name) == (brand, rest)


# ---------------------------------------------------------------- 축약 결과
@pytest.mark.parametrize("full,expected", [
    ("TIGER 미국배당다우존스", "미배당다우"),
    ("KODEX 200커버드콜액티브", "200커콜"),
    ("SOL 미국배당다우존스(H)", "미배당다우(H)"),
    ("PLUS 고배당주", "고배당"),
    ("HANARO 리츠부동산인프라", "리츠인프라"),
    ("KODEX 레버리지", "레버리지"),
    # 지수 제공사 이름과 법적 명칭은 지운다
    ("TIGER 차이나전기차SOLACTIVE", "차이나전기차"),
])
def test_shorten_known_words(full, expected):
    assert pitch_kit.shorten(full) == expected


def test_shorten_fits_in_label_width():
    """일반적인 이름은 이름표 폭(8) 안에 들어간다."""
    samples = [
        "TIGER 미국배당다우존스",
        "KODEX 200커버드콜액티브",
        "TIGER 미국나스닥100커버드콜(합성)",
        "HANARO 리츠부동산인프라",
        "ACE 미국30년국채액티브",
    ]
    for s in samples:
        out = pitch_kit.shorten(s)
        assert pitch_kit.display_width(out) <= pitch_kit.MAX_LABEL_WIDTH, s


# ---------------------------------------------------------------- 안전장치
@pytest.mark.parametrize("full,must_keep", [
    ("KODEX 코스닥150레버리지", "레버리지"),
    ("KODEX 200선물인버스2X", "인버스"),
    ("SOL 미국배당다우존스(H)", "(H)"),
    ("RISE 200고배당커버드콜ATM", "ATM"),
    ("TIGER 미국나스닥100커버드콜(합성)", "(합)"),
])
def test_risk_words_are_never_dropped(full, must_keep):
    """길이를 넘기더라도 상품 성격이 바뀌는 단어는 반드시 남는다."""
    assert must_keep in pitch_kit.shorten(full), full


def test_truncation_does_not_cut_a_number_in_half():
    """'코스닥150레버리지' 를 그냥 자르면 '코스닥1레버리지' 가 되는데, 이건
    '코스닥1' 이라는 없는 지수를 가리키는 것처럼 보여서 원본보다 나쁩니다."""
    out = pitch_kit.shorten("KODEX 코스닥150레버리지")
    assert out == "코스닥레버리지"
    assert "코스닥1" not in out


@pytest.mark.parametrize("full,expected,why", [
    ("KODEX 종합채권(AA-이상)액티브", "종합채권", "괄호가 안 닫힌 채로 끊기면 안 됨"),
    ("TIGER 미국나스닥100커버드콜(합성)", "나스닥100(합)", "'커콜' 이 '커' 로 반토막 나면 안 됨"),
    ("RISE 200고배당커버드콜ATM", "200고배당ATM", "'커콜' 이 '커' 로 반토막 나면 안 됨"),
    ("TIGER 미국배당다우존스타겟커버드콜2호", "미배당다우타겟", "'커콜' 이 '커' 로 반토막 나면 안 됨"),
])
def test_truncation_never_leaves_half_a_word(full, expected, why):
    assert pitch_kit.shorten(full) == expected, why


def test_unknown_etf_does_not_crash_and_is_not_worse_than_before():
    """새로 상장해 사전에 없는 이름도 그냥 잘리기만 하고 예외가 없어야 한다."""
    out = pitch_kit.shorten("두리번자산 초장기우량회사채플러스혼합형")
    assert out
    assert pitch_kit.display_width(out) <= pitch_kit.MAX_LABEL_WIDTH


def test_label_width_budget_is_paired_with_the_frontend():
    """MAX_LABEL_WIDTH 는 전술판 이름표 글자 크기(index.html 의 tagFontPx)와 한 쌍입니다.

    tagFontPx 는 `이름표 안쪽 폭 / 8.8` 로 글자 크기를 정합니다. 여기 값을 올려 놓고
    프론트엔드를 안 고치면, 줄인 이름이 이번엔 화면에서 "…" 로 잘립니다.
    값을 바꿀 일이 있으면 index.html 의 8.8 도 같이 바꾸세요.
    """
    assert pitch_kit.MAX_LABEL_WIDTH == 8.6


def test_shorten_never_returns_empty():
    """군더더기만으로 이뤄진 이름이라도 빈 이름표가 나오면 안 된다."""
    assert pitch_kit.shorten("KODEX 액티브").strip()


# ---------------------------------------------------------------- 유니폼 색
def test_us_wears_stars_and_stripes():
    kit = pitch_kit.kit_of("US", "SCHD")
    assert kit["style"] == "us"
    assert kit["brand"] == ""


def test_kr_wears_brand_colors():
    assert pitch_kit.kit_of("KR", "TIGER 미국배당다우존스")["main"] == "#FF6B00"
    assert pitch_kit.kit_of("KR", "KODEX 200")["main"] == "#1428A0"
    # 리브랜딩 전 이름도 현재 브랜드 색으로
    assert pitch_kit.kit_of("KR", "KBSTAR 200")["main"] == pitch_kit.BRAND_KITS["RISE"][0]


def test_unknown_brand_gets_default_kit():
    kit = pitch_kit.kit_of("KR", "아무개자산 신규ETF")
    assert kit["main"] == pitch_kit.DEFAULT_KIT[0]
    assert kit["brand"] == ""


def test_every_kit_has_three_colors():
    for brand, colors in pitch_kit.BRAND_KITS.items():
        assert len(colors) == 3, brand
        for c in colors:
            assert c.startswith("#") and len(c) == 7, (brand, c)


def test_brand_aliases_point_at_real_brands():
    for old, new in pitch_kit.BRAND_ALIASES.items():
        assert new in pitch_kit.BRAND_KITS, f"{old} -> {new} 는 없는 브랜드"


# ---------------------------------------------------------------- 카드 라벨
def test_card_label_uses_ticker_for_us():
    assert pitch_kit.card_label("US", "SCHD", "Schwab US Dividend Equity ETF") == "SCHD"


def test_card_label_shortens_for_kr():
    assert pitch_kit.card_label("KR", "458730", "TIGER 미국배당다우존스") == "미배당다우"


def test_user_override_wins_over_auto_shortening():
    """자동 축약이 어색하거나 사전에 없는 신규 ETF 일 때의 마지막 수단."""
    assert pitch_kit.card_label("KR", "458730", "TIGER 미국배당다우존스", "내 주력") == "내 주력"
    assert pitch_kit.card_label("US", "SCHD", "Schwab...", "배당왕") == "배당왕"


def test_blank_override_falls_back_to_auto():
    for blank in ("", "   ", None):
        assert pitch_kit.card_label("KR", "458730", "TIGER 미국배당다우존스",
                                    blank or "") == "미배당다우"
