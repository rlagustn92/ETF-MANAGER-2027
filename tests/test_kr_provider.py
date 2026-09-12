"""data/providers/kr_provider.py 테스트 -- 알파벳이 섞인 KRX 코드 지원 (실사용자 리포트로 발견된 버그).

실제로 있었던 문제: "0219E0" 같은 KRX 코드(숫자+영문 혼합, ETN 등에서 흔함)는
isdigit() 조건 때문에 yfinance 접미사(.KS/.KQ)를 안 붙였고, 그 결과 실제로는
존재하는 분배금 데이터를 "없음"으로 잘못 표시했습니다. (실행 확인:
"0219E0.KS" 에는 yfinance 배당 데이터가 실제로 있음, 2026-07-30/08-28 지급)
"""

from data.providers.kr_provider import _yf_symbols


def test_pure_numeric_6digit_code_gets_ks_kq_suffixes():
    assert _yf_symbols("005930") == ["005930.KS", "005930.KQ"]


def test_alphanumeric_6char_code_also_gets_ks_kq_suffixes():
    # 회귀 테스트: 0219E0(ETN류로 추정) 은 예전 코드에서 접미사가 안 붙어 실패했음
    assert _yf_symbols("0219E0") == ["0219E0.KS", "0219E0.KQ"]


def test_non_6char_code_falls_back_to_bare_ticker():
    assert _yf_symbols("12345") == ["12345"]
    assert _yf_symbols("1234567") == ["1234567"]


def test_whitespace_is_stripped():
    assert _yf_symbols(" 005930 ") == ["005930.KS", "005930.KQ"]
