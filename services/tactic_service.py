"""
services/tactic_service.py  --  전술 저장/불러오기 (JSON) (인수인계서 86~89)
=======================================================================

1차 버전은 JSON 내보내기/불러오기를 기본 저장 방식으로 사용합니다.
잘못된 파일을 불러와도 앱 전체가 죽지 않고 명확한 오류 메시지를 돌려줍니다. (인수인계서 89)
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import config
from models.portfolio import Portfolio


@dataclass
class LoadResult:
    ok: bool
    portfolio: Portfolio | None
    message: str = ""


def to_json(portfolio: Portfolio, *, indent: int = 2) -> str:
    return json.dumps(portfolio.to_dict(), ensure_ascii=False, indent=indent)


def export_filename(portfolio: Portfolio) -> str:
    return config.tactic_export_filename(portfolio.name)


def from_json(text: str | bytes) -> LoadResult:
    if isinstance(text, bytes):
        try:
            text = text.decode("utf-8")
        except UnicodeDecodeError:
            return LoadResult(False, None, "파일 인코딩을 읽을 수 없습니다. UTF-8 JSON 이 필요합니다.")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return LoadResult(False, None, f"잘못된 전술 파일입니다. JSON 형식이 아닙니다: {e}")

    if not isinstance(data, dict):
        return LoadResult(False, None, "잘못된 전술 파일입니다. 최상위가 객체(JSON object)가 아닙니다.")

    try:
        portfolio = Portfolio.from_dict(data)
    except ValueError as e:
        return LoadResult(False, None, f"잘못된 전술 파일입니다. 필수 항목을 확인하세요: {e}")
    except Exception as e:  # 예상치 못한 구조도 앱을 죽이지 않음
        return LoadResult(False, None, f"전술 파일을 해석하지 못했습니다: {e}")

    # 스키마/연도 정보는 참고만 (다른 연도 파일도 열 수 있게 허용)
    file_year = data.get(config.TACTIC_FILE_APP_KEY)
    note = ""
    if file_year and file_year != config.APP_YEAR:
        note = (f"참고: 이 전술 파일은 {file_year} 버전에서 저장되었습니다 "
                f"(현재 {config.APP_YEAR}). 정상적으로 불러왔습니다.")
    return LoadResult(True, portfolio, note)
