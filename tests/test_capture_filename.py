"""📸 저장 버튼이 내려받는 PNG 파일 이름 테스트.

여기서 지키려는 것:
- 전술명이 그대로 파일명에 들어가되, 파일명에 못 쓰는 글자는 걸러진다
- 날짜가 붙는다 (같은 전술을 며칠 뒤 다시 저장하면 내용이 다른 그림이므로,
  이름이 같으면 브라우저가 "(1)" 을 붙여 어느 게 언제 것인지 알 수 없게 된다)
- 한글 전술명이 깨지지 않는다
"""

from __future__ import annotations

import re

import config


def test_has_app_name_tactic_name_date_and_png():
    name = config.capture_image_filename("월배당 공격형")
    assert name.startswith("ETF_MANAGER_2027_")
    assert "월배당_공격형" in name
    assert name.endswith(".png")
    assert re.search(r"_\d{8}\.png$", name), name


def test_date_is_korean_today_not_server_date():
    """화면 어디서나 한국 날짜를 씁니다(배포 서버는 UTC 라 하루 어긋날 수 있음)."""
    assert config.today_local().strftime("%Y%m%d") in config.capture_image_filename("t")


def test_illegal_filename_characters_are_removed():
    bad = config.capture_image_filename('내 전술: "공격"/<최강>|?*')
    for ch in '<>:"/\\|?*':
        assert ch not in bad, ch


def test_empty_or_blank_name_still_produces_a_filename():
    for blank in ("", "   "):
        n = config.capture_image_filename(blank)
        assert n.endswith(".png")
        assert "tactic" in n


def test_json_and_png_names_share_the_same_tactic_part():
    """전술 JSON 과 캡처 PNG 가 같은 전술명 규칙을 쓰는지(한 곳에서 관리)."""
    j = config.tactic_export_filename("월배당 공격형")
    p = config.capture_image_filename("월배당 공격형")
    assert "월배당_공격형" in j and "월배당_공격형" in p
