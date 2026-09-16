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
            # "utf-8" 이 아니라 "utf-8-sig" 입니다. 윈도우에서 메모장·엑셀·PowerShell 로
            # 저장하면 파일 맨 앞에 눈에 안 보이는 BOM(﻿) 이 붙는데, 그냥 "utf-8"
            # 로 읽으면 그게 첫 글자가 되어 JSON 파서가 통째로 거절합니다.
            # 사용자 입장에서는 "내가 방금 저장한 내 전술 파일을 앱이 안 열어준다" 입니다.
            # utf-8-sig 는 BOM 이 없으면 utf-8 과 똑같이 동작하므로 잃는 게 없습니다.
            text = text.decode("utf-8-sig")
        except UnicodeDecodeError:
            return LoadResult(False, None, "파일 인코딩을 읽을 수 없습니다. UTF-8 JSON 이 필요합니다.")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return LoadResult(False, None, f"잘못된 전술 파일입니다. JSON 형식이 아닙니다: {e}")

    if not isinstance(data, dict):
        return LoadResult(False, None, "잘못된 전술 파일입니다. 최상위가 객체(JSON object)가 아닙니다.")

    try:
        portfolio, issues = Portfolio.load(data)
    except ValueError as e:
        return LoadResult(False, None, f"잘못된 전술 파일입니다. 필수 항목을 확인하세요: {e}")
    except Exception as e:  # 예상치 못한 구조도 앱을 죽이지 않음
        return LoadResult(False, None, f"전술 파일을 해석하지 못했습니다: {e}")

    # 스키마/연도 정보는 참고만 (다른 연도 파일도 열 수 있게 허용)
    notes: list[str] = []
    file_year = data.get(config.TACTIC_FILE_APP_KEY)
    if file_year and file_year != config.APP_YEAR:
        notes.append(f"참고: 이 전술 파일은 {file_year} 버전에서 저장되었습니다 "
                     f"(현재 {config.APP_YEAR}). 정상적으로 불러왔습니다.")
    # 이상한 값을 고쳐서 담았다면 **반드시** 알립니다. 조용히 고치면 사용자는
    # "내 비중이 왜 0 이지?" 하고 이유를 영영 모릅니다.
    if issues:
        notes.append("불러오면서 아래 값을 고쳤습니다:\n\n"
                     + "\n".join(f"- {m}" for m in issues))
    return LoadResult(True, portfolio, "\n\n".join(notes))
