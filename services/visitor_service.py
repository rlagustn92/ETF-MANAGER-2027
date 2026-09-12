"""
services/visitor_service.py  --  방문자 수 (오늘 / 전체)

왜 외부 서비스를 쓰나
---------------------
배포 서버(Streamlit Cloud)는 앱이 잠들거나 재배포될 때 파일 시스템이 초기화됩니다.
방문자 수를 서버 파일에 적어두면 며칠마다 0 으로 돌아가므로, 숫자만 외부 카운터에 맡깁니다.

무엇을 세나
-----------
**접속 1회(세션 1개)당 1** 입니다. 화면이 다시 그려질 때마다(버튼 클릭 등) 올라가면
숫자가 엉터리가 되므로, app.py 에서 "이번 세션에 이미 셌는지"를 확인하고 한 번만 부릅니다.

- 전체: 키 `total`
- 오늘: 키 `d-YYYY-MM-DD` (한국 날짜 기준. 서버가 UTC 라서 config.today_local() 을 씁니다)

한계 (알고 쓰세요)
------------------
- 같은 사람이 새로고침하거나 다른 기기로 들어오면 각각 세집니다. "정확한 순방문자"가
  아니라 "대략 얼마나 들어오는지" 보는 용도입니다.
- 무료 공개 API 라 누군가 주소를 알아내 숫자를 부풀릴 수 있습니다. 정확한 수치가
  필요하면 Streamlit Cloud 관리 화면의 Analytics 를 보세요(그쪽이 진짜 기준입니다).
- 카운터가 죽어도 앱은 그대로 동작해야 합니다. 모든 실패는 조용히 무시하고 None 을 돌려줍니다.
"""

from __future__ import annotations

import requests

import config


def _namespace() -> str:
    """카운터 이름 공간. 공개 저장소에 그대로 적히면 남이 숫자를 올릴 수 있으므로,
    secrets 에 COUNTER_NS 를 넣으면 그 값을 우선 씁니다."""
    try:
        import streamlit as st
        ns = str(st.secrets.get("COUNTER_NS", "") or "")
        if ns:
            return ns
    except Exception:
        pass
    return config.COUNTER_NAMESPACE_DEFAULT


def _call(action: str, key: str) -> int | None:
    """action: 'hit'(1 올리고 값 반환) | 'get'(값만 읽기). 실패하면 None."""
    url = f"{config.COUNTER_BASE_URL}/{action}/{_namespace()}/{key}"
    try:
        r = requests.get(url, timeout=config.COUNTER_TIMEOUT_SECONDS)
    except requests.RequestException:
        return None
    if r.status_code == 404:
        return 0          # 아직 한 번도 기록되지 않은 키 (예: 오늘 첫 방문 전)
    if r.status_code != 200:
        return None
    try:
        value = r.json().get("value")
    except ValueError:
        return None
    return int(value) if isinstance(value, (int, float)) else None


def count_visit() -> tuple[int, int] | None:
    """이번 접속을 기록하고 (오늘, 전체) 를 돌려줍니다. 실패하면 None.

    ⚠ 세션당 한 번만 부르세요 (app.py 가 session_state 로 보장합니다).
    """
    if not config.COUNTER_ENABLED:
        return None
    today_key = f"d-{config.today_local().isoformat()}"
    today = _call("hit", today_key)
    total = _call("hit", "total")
    if today is None or total is None:
        return None
    return today, total


def read_counts() -> tuple[int, int] | None:
    """숫자를 올리지 않고 읽기만 합니다 (표시 갱신용)."""
    if not config.COUNTER_ENABLED:
        return None
    today = _call("get", f"d-{config.today_local().isoformat()}")
    total = _call("get", "total")
    if today is None or total is None:
        return None
    return today, total
