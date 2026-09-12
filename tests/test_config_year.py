"""연도 변경 구조 테스트 (인수인계서 3, 116).

APP_YEAR 한 곳만 바꾸면 프로그램 전체 명칭이 바뀌어야 합니다.
"""

import ast
import pathlib

import config


def test_app_name_derives_from_year():
    assert config.app_name() == f"ETF MANAGER {config.APP_YEAR}"
    assert config.APP_NAME == f"ETF MANAGER {config.APP_YEAR}"
    assert str(config.APP_YEAR) in config.app_name()
    assert str(config.APP_YEAR) in config.app_name_with_icon()


def test_changing_year_changes_all_derived_names(monkeypatch):
    """APP_YEAR 한 줄만 바꾸면(=여기서는 monkeypatch) 파생 명칭이 모두 바뀐다. (인수인계서 116)"""
    monkeypatch.setattr(config, "APP_YEAR", 2028, raising=True)
    assert config.app_name() == "ETF MANAGER 2028"
    assert config.app_name_with_icon() == "⚽ ETF MANAGER 2028"
    assert config.tactic_export_filename("월배당").startswith("ETF_MANAGER_2028_")


def test_export_filename_sanitizes():
    name = config.tactic_export_filename('나쁜/이름:테스트*?')
    assert "/" not in name and ":" not in name and "*" not in name
    assert name.endswith(".json")


def test_no_hardcoded_year_literals_in_code():
    """주요 모듈의 '코드'(주석/문자열 제외)에 연도 정수 리터럴이 없어야 한다.

    config.py 의 APP_YEAR 정의만 예외. 나머지는 config.APP_YEAR / app_name() 를 써야 한다.
    """
    root = pathlib.Path(config.__file__).parent
    targets = [
        root / "app.py",
        root / "services" / "portfolio_service.py",
        root / "services" / "backtest_service.py",
        root / "services" / "tactic_service.py",
        root / "models" / "portfolio.py",
        root / "models" / "security.py",
    ]
    bad: list[str] = []
    for f in targets:
        if not f.exists():
            continue
        tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, int):
                if node.value in (2027, 2028):
                    bad.append(f"{f.name}:{node.lineno}")
    assert not bad, f"연도 정수 리터럴이 코드에 하드코딩됨: {bad}"
