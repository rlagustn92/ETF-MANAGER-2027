"""
tools/refresh_naver_links.py  --  미국 종목의 네이버 증권 주소 표를 다시 만듭니다.

왜 표를 미리 만들어 두나
------------------------
한국 종목은 코드로 주소를 조립할 수 있지만(`/domestic/stock/{코드}/total`),
**미국은 조립할 수 없습니다.** 티커 뒤에 붙는 거래소 표시가 종목마다 다릅니다.

    SCHD -> /worldstock/etf/SCHD.K      VOO  -> /worldstock/etf/VOO   (아무것도 안 붙음)
    TQQQ -> /worldstock/etf/TQQQ.O      O    -> /worldstock/stock/O/total  (ETF 가 아니라 경로도 다름)

SCHD 와 VOO 는 네이버 기준 **같은 거래소인데 한쪽만 `.K` 가 붙습니다.** 규칙이 없어서
추측해서 만들면 상당수가 빈 페이지로 갑니다. 네이버 자동완성에 물어보는 수밖에 없는데,
사용자가 종목을 누를 때마다 남의 서버를 두드릴 수는 없으니 **자주 쓰는 것은 미리 받아
파일로 박아둡니다.** 여기 없는 티커만 실행 중에 물어봅니다(naver_link_service.py).

실행
----
    python tools/refresh_naver_links.py

data/naver_us_links.py 를 덮어씁니다. 네트워크를 쓰므로 개발자 PC 에서만 돌리세요.
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.providers.us_seed import US_SEED  # noqa: E402

OUT_PATH = ROOT / "data" / "naver_us_links.py"
AC_URL = "https://ac.stock.naver.com/ac"
BASE = "https://m.stock.naver.com"
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://m.stock.naver.com/"}
TIMEOUT = 8

# 네이버가 한 번에 여러 개를 막는 조짐이 보이면 멈춥니다. 남의 서버를 계속 두드리지
# 않기 위한 회로차단기입니다.
FAIL_STREAK_LIMIT = 15


def normalize(ticker: str) -> str:
    """비교·질의용으로 영문/숫자만 남깁니다.

    버크셔 B주가 실제로 이 처리를 필요로 했습니다. 우리 티커는 `BRK-B` 인데 네이버는
    코드를 `BRK B`(공백) 로 들고 있고, 주소는 `/worldstock/stock/BRKb/total` 입니다.
    `BRK-B` 로도 `BRK.B` 로도 검색 결과가 **아예 안 나오고** `BRKB` 로 해야 나옵니다.
    """
    return re.sub(r"[^A-Za-z0-9]", "", str(ticker)).upper()


def lookup(ticker: str, nation: str = "USA") -> str | None:
    """네이버 자동완성에 물어 종목 페이지 주소를 얻습니다. 못 찾으면 None.

    ⚠ 돌려받은 url 을 **그대로** 씁니다. ETF 는 `/worldstock/etf/...`(끝에 /total 없음),
    일반 주식은 `/worldstock/stock/.../total` 로 경로 자체가 다르기 때문에 조립하면 틀립니다.
    """
    want = normalize(ticker)
    if not want:
        return None
    query = urllib.parse.urlencode({"q": want, "target": "stock"})
    req = urllib.request.Request(f"{AC_URL}?{query}", headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None            # 실패하면 링크를 안 겁니다. 추측해서 만들지 않습니다.
    for item in data.get("items") or []:
        # 이름이 비슷한 다른 나라 종목이 같이 옵니다. 코드 완전일치 + 국가로 거릅니다.
        if (normalize(item.get("code", "")) == want
                and item.get("nationCode") == nation
                and item.get("url")):
            return BASE + str(item["url"])
    return None


def previous_count() -> int:
    """기존 표에 몇 개가 들어 있었는지. 파일이 없으면 0."""
    try:
        text = OUT_PATH.read_text(encoding="utf-8")
    except OSError:
        return 0
    return len(re.findall(r'^\s+"', text, re.M))


def render(rows: dict[str, str]) -> str:
    lines = [
        '"""',
        "data/naver_us_links.py  --  미국 종목의 네이버 증권 주소 (자동 생성)",
        "",
        "**손으로 고치지 마세요.** tools/refresh_naver_links.py 가 만듭니다.",
        "",
        "미국은 티커만으로 주소를 조립할 수 없어서(거래소 접미사가 종목마다 다름)",
        "네이버 자동완성에 물어본 결과를 박아둔 표입니다. 여기 있는 종목은 실행 중에",
        "네트워크를 전혀 쓰지 않습니다. 여기 없는 티커만 그때 물어봅니다.",
        "",
        "키는 영문/숫자만 남긴 티커입니다(BRK-B -> BRKB).",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "NAVER_US_LINKS: dict[str, str] = {",
    ]
    for key in sorted(rows):
        lines.append(f'    "{key}": "{rows[key]}",')
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    tickers = [t for (t, _name, _asset) in US_SEED]
    print(f"미국 시드 {len(tickers)}종목을 네이버에 물어봅니다...")

    rows: dict[str, str] = {}
    missing: list[str] = []
    streak = 0
    started = time.time()

    for ticker in tickers:
        url = lookup(ticker)
        if url:
            rows[normalize(ticker)] = url
            streak = 0
        else:
            missing.append(ticker)
            streak += 1
            if streak >= FAIL_STREAK_LIMIT:
                print(f"연속 {streak}건 실패 — 네이버가 막는 것으로 보고 중단합니다.")
                break

    elapsed = time.time() - started
    print(f"성공 {len(rows)} / 실패 {len(missing)} / {elapsed:.1f}초")
    if missing:
        print("  못 찾음:", ", ".join(missing))

    # 네트워크가 반쯤 죽은 상태로 돌려서 멀쩡한 표를 날리는 사고를 막습니다.
    before = previous_count()
    if before and len(rows) < before * 0.8:
        print(f"새 표가 너무 줄었습니다({before} -> {len(rows)}). 덮어쓰지 않습니다.")
        return 1

    OUT_PATH.write_text(render(rows), encoding="utf-8")
    print(f"{OUT_PATH.relative_to(ROOT)} 에 {len(rows)}건을 적었습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
