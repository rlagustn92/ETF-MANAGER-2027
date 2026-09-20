"""
tests/test_naver_link.py  --  네이버 증권 바로가기 주소

네트워크를 쓰지 않습니다. requests 를 가짜로 바꿔서 확인합니다.
"""

from __future__ import annotations

import pytest

import config
from data.providers import cache
from services import naver_link_service as nls


@pytest.fixture(autouse=True)
def _clean_cache():
    """테스트끼리 캐시를 물려받지 않도록 매번 비웁니다."""
    cache.invalidate("naver:")
    yield
    cache.invalidate("naver:")


class FakeResponse:
    def __init__(self, status=200, payload=None, bad_json=False):
        self.status_code = status
        self._payload = payload if payload is not None else {}
        self._bad_json = bad_json

    def json(self):
        if self._bad_json:
            raise ValueError("not json")
        return self._payload


def _explode(*a, **k):
    raise AssertionError("네트워크를 쓰면 안 되는 자리에서 requests.get 이 불렸습니다.")


# ---------------------------------------------------------------- 한국
def test_korean_url_is_built_from_the_code_without_any_network(monkeypatch):
    """한국은 코드만 있으면 주소가 나옵니다. 조립한 주소와 네이버가 알려준 주소가
    같은 것을 069500 / 458730 / 329200 / 0219E0 으로 확인했습니다."""
    monkeypatch.setattr(nls.requests, "get", _explode)
    assert (nls.naver_url("KR", "069500")
            == "https://m.stock.naver.com/domestic/stock/069500/total")
    assert (nls.naver_url("KR", "458730")
            == "https://m.stock.naver.com/domestic/stock/458730/total")


def test_korean_code_with_letters_still_works(monkeypatch):
    """ETN 등은 코드에 영문이 섞입니다(0219E0). 같은 형식으로 동작합니다."""
    monkeypatch.setattr(nls.requests, "get", _explode)
    assert (nls.naver_url("KR", "0219E0")
            == "https://m.stock.naver.com/domestic/stock/0219E0/total")


# ---------------------------------------------------------------- 미국(표)
def test_seeded_us_tickers_need_no_network(monkeypatch):
    """자주 쓰는 미국 종목은 미리 받아둔 표에서 나옵니다."""
    monkeypatch.setattr(nls.requests, "get", _explode)
    assert nls.naver_url("US", "SCHD") == "https://m.stock.naver.com/worldstock/etf/SCHD.K"
    assert nls.naver_url("US", "VOO") == "https://m.stock.naver.com/worldstock/etf/VOO"


def test_the_table_keeps_naver_own_paths_instead_of_guessing():
    """접미사도 경로도 종목마다 다릅니다. 규칙을 만들어 조립하면 빈 페이지로 갑니다.

    VOO 는 접미사가 없고, TQQQ 는 .O 가 붙고, O 는 ETF 가 아니라 경로 자체가 다릅니다.
    """
    from data.naver_us_links import NAVER_US_LINKS as table
    assert table["VOO"].endswith("/etf/VOO")
    assert table["TQQQ"].endswith("/etf/TQQQ.O")
    assert table["O"].endswith("/stock/O/total")


def test_berkshire_b_share_is_matched_despite_the_dash():
    """우리 티커는 BRK-B, 네이버 코드는 'BRK B'(공백), 주소는 BRKb 입니다.

    영문/숫자만 남겨 비교하지 않으면 이 종목만 링크가 안 뜹니다(실제로 그랬습니다).
    """
    assert nls.normalize_ticker("BRK-B") == "BRKB"
    assert nls.normalize_ticker("BRK B") == "BRKB"
    assert nls.naver_url("US", "BRK-B") == "https://m.stock.naver.com/worldstock/stock/BRKb/total"


# ---------------------------------------------------------------- 미국(조회)
def test_unknown_us_ticker_is_looked_up_once_and_then_cached(monkeypatch):
    """표에 없는 티커는 한 번만 물어보고, 그다음부터는 캐시에서 씁니다."""
    calls = []

    def fake_get(url, params=None, **k):
        calls.append(params["q"])
        return FakeResponse(payload={"items": [
            {"code": "ZZTEST", "nationCode": "USA", "url": "/worldstock/etf/ZZTEST.K"}]})

    monkeypatch.setattr(nls.requests, "get", fake_get)
    first = nls.naver_url("US", "ZZTEST")
    second = nls.naver_url("US", "ZZTEST")
    assert first == second == "https://m.stock.naver.com/worldstock/etf/ZZTEST.K"
    assert calls == ["ZZTEST"], "두 번째 호출은 캐시에서 나와야 합니다."


def test_the_returned_url_is_used_as_is(monkeypatch):
    """ETF 는 /etf/...(끝에 /total 없음), 주식은 /stock/.../total 이라 조립하면 틀립니다."""
    monkeypatch.setattr(nls.requests, "get", lambda *a, **k: FakeResponse(payload={
        "items": [{"code": "ZZSTOCK", "nationCode": "USA",
                   "url": "/worldstock/stock/ZZSTOCK.O/total"}]}))
    assert (nls.naver_url("US", "ZZSTOCK")
            == "https://m.stock.naver.com/worldstock/stock/ZZSTOCK.O/total")


def test_a_similar_ticker_from_another_country_is_not_used(monkeypatch):
    """이름이 비슷한 다른 나라 종목이 같이 옵니다. 국가가 다르면 쓰지 않습니다."""
    monkeypatch.setattr(nls.requests, "get", lambda *a, **k: FakeResponse(payload={
        "items": [{"code": "ZZONLY", "nationCode": "JPN", "url": "/worldstock/etf/ZZONLY.T"}]}))
    assert nls.naver_url("US", "ZZONLY") is None


def test_a_different_code_is_not_used(monkeypatch):
    """코드가 완전히 일치할 때만 씁니다(부분 일치 금지)."""
    monkeypatch.setattr(nls.requests, "get", lambda *a, **k: FakeResponse(payload={
        "items": [{"code": "ZZOTHER", "nationCode": "USA", "url": "/worldstock/etf/ZZOTHER"}]}))
    assert nls.naver_url("US", "ZZWANT") is None


# ---------------------------------------------------------------- 실패
@pytest.mark.parametrize("broken", [
    pytest.param(lambda *a, **k: (_ for _ in ()).throw(nls.requests.RequestException("끊김")),
                 id="네트워크_끊김"),
    pytest.param(lambda *a, **k: FakeResponse(status=500), id="서버_오류"),
    pytest.param(lambda *a, **k: FakeResponse(bad_json=True), id="JSON_아님"),
    pytest.param(lambda *a, **k: FakeResponse(payload={"items": []}), id="결과_없음"),
])
def test_failure_returns_none_so_no_link_is_drawn(monkeypatch, broken):
    """실패하면 None 입니다. 그럴듯한 주소를 지어내 빈 페이지로 보내지 않습니다."""
    monkeypatch.setattr(nls.requests, "get", broken)
    assert nls.naver_url("US", "ZZBROKEN") is None


def test_empty_ticker_is_not_looked_up(monkeypatch):
    monkeypatch.setattr(nls.requests, "get", _explode)
    assert nls.naver_url("US", "") is None
    assert nls.naver_url("KR", "   ") is None


def test_timeout_is_short_so_the_panel_is_not_blocked():
    """링크 하나 때문에 화면이 오래 멈추면 안 됩니다."""
    assert 0 < config.NAVER_TIMEOUT_SECONDS <= 5
