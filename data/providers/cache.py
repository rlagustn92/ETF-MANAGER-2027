"""
data/providers/cache.py  --  간단한 TTL 캐시 (인수인계서 57)
===========================================================

불필요한 반복 다운로드를 막습니다.
- 1차: 프로세스 메모리 캐시 (Streamlit 세션 동안 유지)
- 만료시간(TTL)은 config.py 에서 관리하며, 근거 없이 길게 잡지 않습니다.

디스크 캐시는 선택적으로 사용할 수 있으나, 1차 버전은 메모리 캐시만으로 충분합니다.
"""

from __future__ import annotations

import time
from typing import Any, Callable

_STORE: dict[str, tuple[float, Any]] = {}


def get_or_set(key: str, ttl_seconds: int, producer: Callable[[], Any]) -> Any:
    """key 에 유효한 캐시가 있으면 반환, 없으면 producer() 실행 후 저장.

    producer 가 예외를 던지면 캐시에 저장하지 않고 그대로 전파합니다.
    (실패를 캐싱하지 않음 -- 다시 시도 버튼이 동작하도록)
    """
    now = time.time()
    hit = _STORE.get(key)
    if hit is not None and (now - hit[0]) < ttl_seconds:
        return hit[1]
    value = producer()
    _STORE[key] = (now, value)
    return value


def invalidate(prefix: str | None = None) -> int:
    """캐시 무효화. prefix 를 주면 해당 접두사로 시작하는 키만 삭제.

    '데이터 업데이트' 버튼(인수인계서 56)이 전체 무효화에 사용합니다.
    삭제한 항목 수를 반환합니다.
    """
    global _STORE
    if prefix is None:
        n = len(_STORE)
        _STORE = {}
        return n
    keys = [k for k in _STORE if k.startswith(prefix)]
    for k in keys:
        _STORE.pop(k, None)
    return len(keys)


def stats() -> dict:
    return {"entries": len(_STORE), "keys": sorted(_STORE.keys())}
