"""
components/local_store/  --  브라우저 저장소(localStorage) 통로

Streamlit 은 서버에서 화면을 그려서 브라우저 저장소에 직접 손을 댈 수 없습니다.
컴포넌트는 iframe 안에서 도는 진짜 브라우저 코드라, 여기서 읽고 써서 값을
파이썬으로 올려보냅니다.

쓰는 법 (app.py)
----------------
읽기는 **화면 맨 위**에서, 쓰기는 **맨 아래**에서 부릅니다.

    # 맨 위 -- 위젯이 하나라도 만들어지기 전이어야 합니다.
    got = local_store(mode="read", key="ls_read")

    ... 화면 ...

    # 맨 아래 -- 이번 렌더에서 사용자가 고친 내용까지 반영된 뒤
    local_store(mode="write", data=json_text, key="ls_write")

왜 위/아래로 나누나
-------------------
복원한 값을 session_state 에 넣으려면 **위젯이 만들어지기 전**이어야 합니다
(만들어진 뒤에 고치면 StreamlitWidgetAlreadyInstantiatedError). 반대로 저장할
값은 사용자가 이번에 고친 것까지 반영돼야 하므로 화면을 다 그린 뒤라야 합니다.
한 번의 호출로는 둘 다 만족할 수 없어서 두 번 부릅니다.

반환값
------
읽기: {"mode":"read", "ok":bool, "data":str|None, "err":str, "writable":bool}
쓰기: {"mode":"write", "ok":bool, "err":str}
최초 렌더에는 None (아직 브라우저가 답하기 전).

`writable` 의 한계
------------------
저장소에 한 번 써보고 지워봐서 판단합니다. 사파리 시크릿 모드처럼 **예외를 던지는**
경우는 잡히지만, **크롬 시크릿 모드는 쓰기가 성공합니다**(창을 닫을 때 지워질 뿐).
그래서 writable=True 라고 해서 "안전하게 남는다"는 뜻은 아닙니다.
평소 안내 문구로 "이 브라우저에만 저장됩니다"를 항상 같이 보여줘야 하는 이유입니다.
"""

from __future__ import annotations

import os

import streamlit.components.v1 as components

_FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")

_component_func = components.declare_component("etf_local_store", path=_FRONTEND_DIR)

# 저장소 칸 이름. 바꾸면 기존 사용자의 저장 내용이 **안 보이게 됩니다**
# (지워지는 건 아니고, 앱이 다른 칸을 보게 됩니다). 함부로 바꾸지 마세요.
STORAGE_KEY = "etf_manager_2027_v1"


def local_store(*, mode: str = "read", data: str | None = None,
                storage_key: str = STORAGE_KEY, key: str | None = None):
    """브라우저 저장소를 읽거나(mode="read") 씁니다(mode="write")."""
    return _component_func(
        mode=mode,
        data=data,
        storage_key=storage_key,
        key=key,
        default=None,
    )
