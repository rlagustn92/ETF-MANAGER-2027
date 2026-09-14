"""
pitch_kit.py  --  전술판 카드(유니폼)의 "이름"과 "색"을 만드는 곳
==================================================================

전술판 카드는 축구 유니폼 모양입니다.
  - 유니폼 색   = 운용사 브랜드 (KODEX=남색, TIGER=주황 ...)
  - 등번호      = 살(BUY) 비율
  - 아래 이름표 = 짧게 줄인 종목명

왜 이 파일이 필요한가
---------------------
미국 종목은 티커가 곧 이름이라 짧습니다 ("SCHD").
그런데 한국 ETF 는 이름이 너무 깁니다.

    TIGER 미국배당다우존스            16자
    KODEX 200커버드콜액티브           17자
    TIGER 미국나스닥100커버드콜(합성)  24자

카드 폭에는 한글 8자 정도밖에 안 들어가서, 예전에는 "TIGER 미국배…" 처럼
잘려 나와 무슨 종목인지 알 수 없었습니다.

어떻게 줄이는가 (핵심)
----------------------
**종목 사전이 아니라 "단어 사전"입니다.**
국내 ETF 는 900개가 넘고 매달 새로 나오므로, 종목을 하나씩 적어두는 방식은
절대 유지할 수 없습니다. 대신 한국 ETF 이름이 늘 같은 부품으로 조립된다는
점을 이용합니다.

    [운용사 브랜드] + [기초자산] + [전략] + [꼬리표]
       TIGER          미국배당다우존스
       KODEX             200        커버드콜   액티브

그래서 아래 4단계만 거치면 새로 상장한 ETF 도 대부분 자동으로 처리됩니다.

    1) 브랜드 떼기      TIGER 미국배당다우존스 -> (TIGER, 미국배당다우존스)
    2) 군더더기 삭제    "액티브", "증권상장지수투자신탁", 지수사명 ...
    3) 단어 치환        미국배당다우존스 -> 미배당다우,  커버드콜 -> 커콜
    4) 길이 초과 시 자름 (정식 이름은 상세 패널·캡처 명단에 그대로 남음)

모르는 단어가 나와도 망가지지 않습니다. 3단계를 건너뛰고 앞부분만 보여줄
뿐이라, 최악이어도 지금(그냥 잘림)보다 나빠지지 않습니다.

⚠️ 절대 지우면 안 되는 단어
---------------------------
축약은 "편하게 보려고" 하는 것이지 정보를 없애는 게 아닙니다.
위험도나 상품 성격이 바뀌는 단어는 글자 수를 넘기더라도 반드시 남깁니다.
KEEP_TOKENS 를 보세요. 예를 들어 "레버리지"를 지우면 2배 상품을 일반
상품으로 오해하게 되고, "(H)" 를 지우면 환헤지 여부가 사라집니다.

유지보수
--------
새 단어가 나오면 이 파일의 표에 한 줄만 추가하면 됩니다.
종목이 900개든 2000개든 상관없습니다.
"""

from __future__ import annotations

import re

# =====================================================================
# 1. 운용사 브랜드 -> 유니폼 색
# =====================================================================
# (메인색, 짙은색, 글씨색)
#   메인색   : 유니폼 몸통
#   짙은색   : 유니폼 테두리 + 이름표 배경  (사용자가 고른 "짙은 브랜드색" 방식)
#   글씨색   : 유니폼 위 등번호 색
#
# 각 운용사 CI 에서 고른 색이되, 전술판에서 서로 구분돼야 하므로 겹치는 것은
# 비틀었습니다. (예: 한화 PLUS 도 원래 주황 계열이라 미래에셋 TIGER 와 겹쳐서
# 보라로 조정)
BRAND_KITS: dict[str, tuple[str, str, str]] = {
    "KODEX":     ("#1428A0", "#0A1660", "#FFFFFF"),   # 삼성자산운용
    "TIGER":     ("#FF6B00", "#9E4200", "#FFFFFF"),   # 미래에셋자산운용
    "ACE":       ("#E4002B", "#8C0019", "#FFFFFF"),   # 한국투자신탁운용
    "SOL":       ("#00A3E0", "#006C94", "#FFFFFF"),   # 신한자산운용
    "RISE":      ("#FFC220", "#A37800", "#3A2A00"),   # KB자산운용
    "HANARO":    ("#00A651", "#00642F", "#FFFFFF"),   # NH아문디자산운용
    "PLUS":      ("#6E48AA", "#40296A", "#FFFFFF"),   # 한화자산운용
    "KOSEF":     ("#C8102E", "#7A0A1C", "#FFFFFF"),   # 키움투자자산운용
    "TIMEFOLIO": ("#2D3A45", "#161E25", "#FFFFFF"),
    "WON":       ("#0072CE", "#004880", "#FFFFFF"),   # 우리자산운용
    "BNK":       ("#E5711E", "#8C4210", "#FFFFFF"),
    "히어로즈":   ("#7A5C3E", "#463424", "#FFFFFF"),
}

# 브랜드가 바뀐 상품들 (리브랜딩). 옛 이름으로 들어와도 현재 브랜드로 맞춥니다.
BRAND_ALIASES: dict[str, str] = {
    "KBSTAR": "RISE",      # KB자산운용, 2024 리브랜딩
    "ARIRANG": "PLUS",     # 한화자산운용, 2024 리브랜딩
    "KINDEX": "ACE",       # 한국투자신탁운용, 2022 리브랜딩
    "네비게이터": "TIMEFOLIO",
}

# 브랜드를 못 알아봤을 때 입는 기본 유니폼 (회색)
DEFAULT_KIT: tuple[str, str, str] = ("#8E99A6", "#4A535C", "#FFFFFF")

# 미국 종목은 브랜드색 대신 "성조기 원정 유니폼"을 입습니다.
# 흰 몸통 + 빨간 소매 + 가슴에 큰 성조기. 이름표는 남색.
US_KIT: tuple[str, str, str] = ("#F8F8F4", "#0A2B5C", "#0A2B5C")


# =====================================================================
# 2. 이름 축약 규칙
# =====================================================================
# 2단계: 통째로 지우는 군더더기.
#   - "액티브" 는 요즘 신상품 대부분에 붙어 있어서 종목 구분에 도움이 안 됩니다.
#   - 법적 명칭과 지수 제공사 이름도 화면에서는 의미가 없습니다.
DROP_PATTERNS: tuple[str, ...] = (
    "증권상장지수투자신탁",
    "상장지수투자신탁",
    "증권투자신탁",
    "SOLACTIVE",
    "Solactive",
    "iSelect",
    "액티브",
)

# 3단계: 단어 치환. **반드시 긴 것부터** 적용해야 합니다.
#   ("미국배당다우존스" 를 먼저 잡지 않으면 "커버드콜" 규칙이 엉뚱하게 끼어듭니다)
REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("미국배당다우존스", "미배당다우"),
    ("리츠부동산인프라", "리츠인프라"),
    ("미국나스닥100", "나스닥100"),
    ("미국S&P500", "S&P500"),
    ("미국대표빅테크", "빅테크"),
    ("종합채권", "종합채권"),
    ("머니마켓", "MMF"),
    ("커버드콜", "커콜"),
    ("고배당주", "고배당"),
    ("배당성장", "배당성장"),
    ("(합성)", "(합)"),
    ("단기채권", "단기채"),
    ("국고채권", "국고채"),
)

# ⚠️ 4단계에서 길이가 넘쳐도 **끝까지 살리는** 단어.
#    지우면 상품 성격이나 위험도가 달라져서, 잘못 사면 손해로 이어집니다.
KEEP_TOKENS: tuple[str, ...] = (
    "레버리지",   # 2배. 지우면 일반 상품으로 오해
    "인버스",     # 하락 베팅
    "2X", "3X",
    "(H)",        # 환헤지 여부
    "(합)",
    "ATM", "OTM",  # 커버드콜 행사가 -- 성격이 완전히 다름
    "TR",         # 토탈리턴. 분배금이 안 나오는데 배당 ETF 로 착각하면 큰일
)

# 치환으로 만들어 둔 짧은 단어들은 "통째로 하나"로 취급해서, 자를 때 반토막
# 나지 않게 합니다. ("커콜" 이 "커" 로 남으면 아무 뜻도 없는 글자가 됩니다)
_ATOMIC_TOKENS: tuple[str, ...] = tuple(sorted(
    {dst for _, dst in REPLACEMENTS if dst} | set(KEEP_TOKENS),
    key=len, reverse=True,
))

# 글자별 폭 (한글 1.0 기준). 눈대중이 아니라 실제 브라우저에서
# measureText 로 잰 값입니다(이름표 글꼴 = Segoe UI + Noto Sans KR/맑은 고딕):
#     한글 0.92em · 대문자 0.703 · 숫자 0.575 · 소문자 0.538 · 괄호 0.369
# 이걸 한글=1.0 으로 정규화한 값이 아래입니다.
_W_HANGUL = 1.0
_W_UPPER = 0.764
_W_DIGIT = 0.625
_W_LOWER = 0.585
_W_PUNCT = 0.400
_W_ASCII_ETC = 0.620

# 이름표에 들어가는 최대 "표시 폭".
# 실측: 이름표 안쪽 폭 84px / 글꼴 10px => 한글 9.1자분. 위 계수에 ±0.25 정도
# 오차가 있으므로 여유를 두고 8.6 으로 잡습니다.
MAX_LABEL_WIDTH: float = 8.6


def display_width(text: str) -> float:
    """한글은 영문보다 두 배 가까이 넓으므로 글자 수 대신 '폭'으로 셉니다."""
    w = 0.0
    for ch in text:
        if not ch.isascii():
            w += _W_HANGUL
        elif ch.isdigit():
            w += _W_DIGIT
        elif ch.isupper():
            w += _W_UPPER
        elif ch.islower():
            w += _W_LOWER
        elif ch in "()[]{}.,'\"·-_ ":
            w += _W_PUNCT
        else:
            w += _W_ASCII_ETC
    return w


def _protected_spans(text: str) -> list[tuple[int, int]]:
    """이 구간 한가운데서는 자르면 안 된다는 표시.

    - 치환으로 만들어 둔 짧은 단어("커콜", "미배당다우" ...): 반토막 나면
      "200고배당커ATM" 처럼 없는 말이 됩니다.
    - 괄호 묶음: "종합채권(AA-이" 처럼 괄호가 안 닫히면 더 지저분합니다.
    """
    spans: list[tuple[int, int]] = []
    for m in re.finditer(r"\([^)]*\)?", text):       # 닫히지 않은 괄호도 잡음
        spans.append((m.start(), m.end()))
    for tok in _ATOMIC_TOKENS:
        start = 0
        while (i := text.find(tok, start)) >= 0:
            spans.append((i, i + len(tok)))
            start = i + 1
    return spans


def _truncate_to_width(text: str, budget: float) -> str:
    """폭에 맞춰 자르되, 말이 반토막 나는 자리는 피합니다.

    그냥 자르면 이런 것들이 나옵니다(전부 원본보다 나쁨):
        코스닥150레버리지    -> 코스닥1레버리지   ("코스닥1" 이라는 지수는 없음)
        종합채권(AA-이상)    -> 종합채권(AA-이    (괄호가 안 닫힘)
        200고배당커콜ATM     -> 200고배당커ATM   ("커" 는 말이 아님)
    """
    if display_width(text) <= budget:
        return text

    cut_at = len(text)
    acc = 0.0
    for i, ch in enumerate(text):
        step = display_width(ch)
        if acc + step > budget:
            cut_at = i
            break
        acc += step

    # 보호 구간 한가운데면 그 구간 시작으로 물러섭니다(겹칠 수 있어 반복).
    spans = _protected_spans(text)
    for _ in range(len(spans) + 1):
        moved = False
        for s, e in spans:
            if s < cut_at < e:
                cut_at, moved = s, True
        if not moved:
            break

    out = text[:cut_at]
    # 숫자 한가운데서 끊겼으면 그 숫자 뭉치를 통째로 버립니다.
    if out and out[-1].isdigit() and cut_at < len(text) and text[cut_at].isdigit():
        out = out.rstrip("0123456789")
    return out.rstrip(" -_·(")


def split_brand(name: str) -> tuple[str, str]:
    """'TIGER 미국배당다우존스' -> ('TIGER', '미국배당다우존스').

    브랜드를 못 찾으면 ('', 원래이름) 을 돌려줍니다.
    """
    s = (name or "").strip()
    if not s:
        return "", ""
    # 브랜드는 맨 앞 토큰입니다. 붙여 쓴 경우("KODEX200...")도 있어서 접두사로 봅니다.
    candidates = sorted(
        set(BRAND_KITS) | set(BRAND_ALIASES), key=len, reverse=True,
    )
    upper = s.upper()
    for cand in candidates:
        if upper.startswith(cand.upper()):
            rest = s[len(cand):].strip()
            brand = BRAND_ALIASES.get(cand.upper(), cand.upper())
            if brand not in BRAND_KITS:
                brand = BRAND_ALIASES.get(cand, cand)
            return brand, rest
    return "", s


def shorten(name: str, max_width: float = MAX_LABEL_WIDTH) -> str:
    """긴 한국 ETF 이름을 이름표에 들어갈 만큼 줄입니다.

    모르는 단어가 나와도 예외 없이 동작합니다(치환을 건너뛰고 자르기만 함).
    """
    _, rest = split_brand(name)
    s = rest or (name or "").strip()

    # 2단계: 군더더기 제거
    for pat in DROP_PATTERNS:
        s = s.replace(pat, "")

    # 3단계: 단어 치환 (긴 것부터)
    for src, dst in sorted(REPLACEMENTS, key=lambda p: len(p[0]), reverse=True):
        s = s.replace(src, dst)

    s = re.sub(r"\s+", " ", s).strip(" -_·")
    if not s:
        # 브랜드만 있고 나머지가 통째로 지워진 이상한 경우 -> 원래 이름으로 되돌림
        return _truncate_to_width((name or "").strip(), max_width)

    # 4단계: 길이 맞추기. 단, KEEP_TOKENS 는 끝까지 살립니다.
    tail = ""
    body = s
    for tok in KEEP_TOKENS:
        if body.endswith(tok):
            tail = tok + tail
            body = body[: -len(tok)].rstrip()
            break

    if display_width(body) + display_width(tail) > max_width:
        # tail 이 아무리 길어도 tail 은 안 자릅니다(위험 정보). 몸통만 줄입니다.
        budget = max(1.5, max_width - display_width(tail))
        body = _truncate_to_width(body, budget)

    return (body + tail).strip()


# =====================================================================
# 3. 종목 하나 -> 카드에 필요한 모든 표시 정보
# =====================================================================
def kit_of(market: str, name: str) -> dict:
    """유니폼 색 정보. 미국은 성조기 키트, 한국은 브랜드 키트."""
    if str(market).upper() == "US":
        main, dark, text = US_KIT
        return {"style": "us", "brand": "", "main": main, "dark": dark, "text": text}
    brand, _ = split_brand(name)
    main, dark, text = BRAND_KITS.get(brand, DEFAULT_KIT)
    return {"style": "solid", "brand": brand, "main": main, "dark": dark, "text": text}


def card_label(market: str, ticker: str, display_name: str, override: str = "") -> str:
    """이름표에 찍을 글자.

    override 가 있으면 사용자가 직접 정한 이름이므로 그대로 씁니다(자동 축약이
    마음에 안 들거나, 사전에 없는 신규 ETF 인 경우의 마지막 수단).
    미국은 티커가 곧 이름이라 줄일 필요가 없습니다.
    """
    if override and override.strip():
        return override.strip()
    if str(market).upper() == "US":
        return (ticker or display_name or "").strip()
    return shorten(display_name or ticker or "")
