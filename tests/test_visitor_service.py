"""방문자 카운터 테스트 (네트워크 없이).

가장 중요한 두 가지:
1) 카운터가 죽어도 **앱은 멀쩡해야 합니다.** 모든 실패는 None 으로 조용히 처리.
2) '오늘'은 **한국 날짜** 여야 합니다. 배포 서버는 UTC 라서 그냥 today() 를 쓰면
   한국 시간 오전 9시 이전에는 어제 칸에 세어집니다.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
import requests

import config
from services import visitor_service as vs


class FakeResp:
    def __init__(self, payload=None, status=200):
        self._payload = payload if payload is not None else {}
        self.status_code = status

    def json(self):
        if self._payload == "bad":
            raise ValueError("not json")
        return self._payload


def test_counts_are_returned_as_today_and_total(monkeypatch):
    seen = []

    def fake_get(url, timeout=None):
        seen.append(url)
        return FakeResp({"value": 7 if "d-" in url else 123})

    monkeypatch.setattr(requests, "get", fake_get)
    assert vs.count_visit() == (7, 123)
    assert any("/hit/" in u and "/d-" in u for u in seen)   # 오늘 키
    assert any(u.endswith("/total") for u in seen)          # 전체 키


def test_today_key_uses_korean_date_not_server_date(monkeypatch):
    """서버가 UTC 라도 '오늘'은 한국 날짜로 세어야 한다."""
    seen = []
    monkeypatch.setattr(requests, "get",
                        lambda url, timeout=None: (seen.append(url), FakeResp({"value": 1}))[1])
    monkeypatch.setattr(config, "today_local", lambda: date(2026, 9, 12))

    vs.count_visit()
    assert any("/d-2026-09-12" in u for u in seen), seen


def test_korean_date_helper_is_nine_hours_ahead_of_utc():
    kst = config.now_local()
    utc_offset_hours = kst.utcoffset().total_seconds() / 3600
    assert utc_offset_hours == 9
    # UTC 자정 직후(= 한국 오전 9시)에도 날짜가 어긋나지 않는지 개념 확인
    assert config.today_local() == config.now_local().date()


def test_network_failure_returns_none_and_does_not_raise(monkeypatch):
    def boom(url, timeout=None):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(requests, "get", boom)
    assert vs.count_visit() is None      # 앱이 죽으면 안 됨


def test_server_error_returns_none(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda url, timeout=None: FakeResp(status=500))
    assert vs.count_visit() is None


def test_bad_json_returns_none(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda url, timeout=None: FakeResp("bad"))
    assert vs.count_visit() is None


def test_missing_key_counts_as_zero(monkeypatch):
    """오늘 첫 방문 전이면 그 날짜 키가 아직 없습니다(404). 0 으로 봐야 합니다."""
    monkeypatch.setattr(requests, "get",
                        lambda url, timeout=None: FakeResp(status=404) if "/d-" in url
                        else FakeResp({"value": 50}))
    assert vs.count_visit() == (0, 50)


def test_read_counts_does_not_increment(monkeypatch):
    seen = []
    monkeypatch.setattr(requests, "get",
                        lambda url, timeout=None: (seen.append(url), FakeResp({"value": 3}))[1])
    vs.read_counts()
    assert all("/get/" in u for u in seen), seen
    assert not any("/hit/" in u for u in seen)


def test_disabled_switch_skips_network_entirely(monkeypatch):
    monkeypatch.setattr(config, "COUNTER_ENABLED", False)
    monkeypatch.setattr(requests, "get",
                        lambda *a, **k: pytest.fail("꺼져 있으면 호출하면 안 됨"))
    assert vs.count_visit() is None
    assert vs.read_counts() is None


def test_timeout_is_short_so_page_load_is_not_blocked():
    """카운터가 느려도 화면을 오래 붙잡으면 안 됩니다."""
    assert config.COUNTER_TIMEOUT_SECONDS <= 3


def test_last_updated_is_korean_time():
    """화면에 'KST' 라고 적히므로 계산도 한국 시간이어야 한다 (UTC 서버 대응)."""
    from services import portfolio_service
    from models.portfolio import Portfolio

    comp = portfolio_service.compute(Portfolio(name="t", initial_capital_krw=1_000_000))
    assert isinstance(comp.last_updated, datetime)
    assert comp.last_updated.utcoffset() is not None, "시간대 정보가 있어야 합니다"
    assert comp.last_updated.utcoffset().total_seconds() / 3600 == 9
