"""'데이터 업데이트'(캐시 비우기)는 관리자만 볼 수 있어야 한다 (사용자 요청).

캐시는 모든 접속자가 공유하므로, 아무나 비울 수 있으면 한 명이 누를 때마다 전체 시세를
다시 받아오게 되어 데이터 제공처의 요청 한도에 걸립니다.
"""

from __future__ import annotations

import pathlib

from streamlit.testing.v1 import AppTest

APP_PATH = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")

UPDATE_LABEL = "🔄 데이터 업데이트"


def _run(market, *, secrets=None, query=None):
    market.set_fx(rate=1_400.0)
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    if secrets:
        for k, v in secrets.items():
            at.secrets[k] = v
    if query:
        at.query_params.update(query)
    at.run()
    assert not at.exception
    return at


def _labels(at):
    return [b.label for b in at.button]


def test_admin_key_unset_means_personal_use_button_visible(market):
    """개인 PC 에서 혼자 쓸 때는 그냥 보여야 한다 (ADMIN_KEY 미설정)."""
    at = _run(market)
    assert UPDATE_LABEL in _labels(at)


def test_button_is_hidden_for_normal_visitors(market):
    at = _run(market, secrets={"ADMIN_KEY": "s3cret"})
    assert UPDATE_LABEL not in _labels(at)
    # 대신 자동 갱신 안내가 보여야 한다
    assert any("자동으로 갱신" in c.value for c in at.caption)


def test_button_is_hidden_with_a_wrong_key(market):
    at = _run(market, secrets={"ADMIN_KEY": "s3cret"}, query={"admin": "guess"})
    assert UPDATE_LABEL not in _labels(at)


def test_button_appears_with_the_right_key(market):
    at = _run(market, secrets={"ADMIN_KEY": "s3cret"}, query={"admin": "s3cret"})
    assert UPDATE_LABEL in _labels(at)
