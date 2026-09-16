"""
services/backtest_service.py  --  단순 Buy & Hold 백테스트 (인수인계서 66~77)
=========================================================================

답하려는 질문 (인수인계서 66):
    "내가 이 전술을 특정 날짜부터 운용했다면 지금 얼마가 되었나?"

방식:
    시작일에 과거 종가로 매수 -> 이후 리밸런싱 없음 -> 최신 데이터 기준일에 평가.
    분배금은 재투자하지 않음(1차 버전). 옵션으로 현금 수령 합산만 가능. (인수인계서 75, 76)
    수수료/세금/슬리피지/환전비용 미반영. (인수인계서 77)

가격/환율/분할 처리 (인수인계서 51, 62~65, 72, 112)
--------------------------------------------------
- 미국 종목: 과거 종가 x "그 날짜의" USD/KRW (과거 환율). "과거 주가 + 현재 환율" 금지.
- 주식분할: yfinance 의 history(auto_adjust=False) 종가와 .dividends 는
  '이미 모든 분할을 소급 반영(split-adjusted)' 한 값임을 실행으로 확인했습니다.
    예) AAPL 2020-01-02 Close = 75.09 = 원본 300.35 / 4 (2020 4:1 분할)
        NVDA 2019 배당 = 0.004 = 원본 0.16 / 40 (4:1 x 10:1)
  따라서 매수/평가에 같은 종가 계열을 쓰면 분할로 인한 왜곡이 없습니다.
  보유수량에 분할비율을 '추가로' 곱하면 이중 반영이 되므로 하지 않습니다.
  .splits 데이터는 '구간 내 분할이 있었는지' 표시(정합성 참고)용으로만 사용합니다.
- 한국 종목: FinanceDataReader 종가도 수정주가이므로 동일하게 추가 조정하지 않습니다.

- 시작일이 거래일이 아니면 "이후 첫 공통 거래일" 로 이동, 입력일과 실제 매수일을 모두 표시. (인수인계서 70)
- 시작일보다 늦게 상장된 종목이 있으면 백테스트 불가. (인수인계서 71)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

import config
from data.providers import fx_provider
from data.providers.base import DataUnavailable, HISTORY_CLOSE_COL
from data.providers.registry import get_provider
from models.portfolio import Portfolio
from models.security import (DIST_METHOD_MANUAL, MARKET_KR, MARKET_US,
                             Security)
from services import calculation_service as calc

# 시작일과 종목 데이터 시작일의 허용 격차(휴장/연휴). 이보다 크면 "상장 이후" 로 판단.
LISTING_TOLERANCE_DAYS = 10


def capture_rows(result: "BacktestResult") -> list[dict]:
    """백테스트 결과를 **이미지로 그릴 때** 쓰는 모양 (components/table_capture).

    ⚠ 최대낙폭을 뺀 그림은 만들지 않습니다. 수익만 담긴 그림이 커뮤니티로 퍼지면
      그건 계산 결과가 아니라 광고가 됩니다. 화면에서 지키는 규칙을 그림에서도
      똑같이 지킵니다.
    """
    from formatting import won_short

    years = 0.0
    if result.actual_buy_date and result.data_as_of:
        years = (result.data_as_of - result.actual_buy_date).days / 365.25
    on_invested = (result.profit_krw / result.total_invested_krw * 100.0
                   if result.total_invested_krw > 0 else 0.0)

    out = [
        {"cells": [{"t": "기간"},
                   {"t": f"{result.actual_buy_date} ~ {result.data_as_of} ({years:.1f}년)"}]},
        {"cells": [{"t": "초기 투자금"}, {"t": won_short(result.initial_capital_krw)}]},
        # 합계는 합계라고 부르고, 바로 아래에서 쪼갭니다. 한 칸에 주식·현금·분배금을
        # 뭉쳐 놓으면 얼마가 주가로 번 것인지 알 수가 없습니다. 그림은 맥락 없이
        # 퍼지므로 화면보다 더 분명해야 합니다.
        {"cells": [{"t": "최종 자산 (합계)"},
                   {"t": won_short(result.final_value_krw),
                    **({"win": True} if result.profit_krw > 0 else {})}]},
        {"cells": [{"t": "└ 주식 평가액"},
                   {"t": won_short(result.holdings_value_krw), "dim": True}]},
        {"cells": [{"t": "└ 잔여현금"},
                   {"t": won_short(result.cash_balance_krw), "dim": True}]},
    ]
    if result.include_distributions:
        out.append({"cells": [{"t": "└ 받은 분배금 (세전)"},
                              {"t": won_short(result.distributions_cash_krw), "dim": True}]})
    out += [
        {"cells": [{"t": "수익률 (투자금 기준)"},
                   {"t": f"{on_invested:+.2f}%",
                    **({"win": True} if on_invested > 0 else {})}],
         "sep": True},
        {"cells": [{"t": "도중 최대낙폭"},
                   {"t": (f"{result.max_drawdown_pct:.1f}%"
                          + (f" ({result.max_drawdown_date:%Y년 %m월})"
                             if result.max_drawdown_date else ""))
                    if result.max_drawdown_pct < 0 else "계산 못 함"}]},
        # 시드 전부가 종목에 들어가는 일은 드물어서, 이게 없으면 "1억이 1억 2천" 만
        # 보이고 그중 얼마가 현금이었는지가 사라집니다.
        {"cells": [{"t": "총 원금 (종목에 들어간 돈)"},
                   {"t": won_short(result.total_invested_krw), "dim": True}]},
        {"cells": [{"t": "담은 종목"}, {"t": f"{len(result.rows)}개"}]},
    ]
    return out


def capture_notes(result: "BacktestResult") -> list[str]:
    """그림 아래 붙일 안내. **화면과 같은 말**이어야 합니다."""
    notes = [config.BACKTEST_DISCLAIMER, "지난 성과가 앞으로를 보장하지 않습니다."]
    if result.include_distributions:
        # 낙폭은 분배금을 빼고 잽니다(_max_drawdown 참고). 같은 그림 안에 두 숫자가
        # 나란히 있으니, 기준이 다르다는 것을 말해두지 않으면 어긋나 보입니다.
        notes.insert(0, "받은 분배금은 재투자하지 않고 현금으로 쌓았습니다(세전). "
                        "최대낙폭은 그 현금을 빼고 잰 값입니다 — 넣으면 하락이 "
                        "실제보다 작아 보입니다.")
    return notes


def capture_holdings(result: "BacktestResult") -> dict:
    """종목별 표 -- **화면에 떠 있는 표와 같은 칸, 같은 순서**.

    왜 요약만으로는 안 되나
    -----------------------
    요약만 담은 그림은 "1억이 1억 3천이 됐다" 는 숫자만 남고 **무엇을 담아서
    그렇게 됐는지** 가 빠집니다. 그건 근거 없는 결과 자랑이 됩니다. 화면에서
    바로 아래 붙어 있는 종목별 표까지 같이 담아야 그림 한 장이 말이 됩니다.
    """
    from formatting import native_amt

    columns = ["종목", "살(BUY) 비율", "매수가", "살 때 환율", "수량",
               "살 때 원금(₩)", "구간내 분할", "종료가", "평가금액(₩)", "지금 환율"]
    rows = []
    for x in result.rows:
        name = x.display_name if x.market == MARKET_KR else x.ticker
        rows.append({"cells": [
            {"t": name},
            {"t": f"{x.target_weight * 100:.2f}%"},
            {"t": f"{native_amt(x.buy_price_native, x.currency)} {x.currency}"},
            {"t": (f"{x.buy_fx:,.2f}" if x.buy_fx else "–"), "dim": True},
            {"t": f"{x.shares:g}"},
            {"t": f"{x.invested_krw:,.0f}"},
            {"t": str(x.splits_in_period), "dim": True},
            {"t": f"{native_amt(x.final_price_native, x.currency)} {x.currency}"},
            {"t": f"{x.final_value_krw:,.0f}"},
            {"t": (f"{x.final_fx:,.2f}" if x.final_fx else "–"), "dim": True},
        ]})
    return {"heading": "종목별", "columns": columns, "rows": rows}


def capture_sections(result: "BacktestResult") -> list[dict]:
    """그림 한 장에 들어갈 표 전부 (요약 + 종목별).

    화면에서 보이는 것이 그대로 그림에 들어가야 합니다 -- 저장 버튼을 누른 사람은
    "지금 보고 있는 이 화면" 이 저장될 거라고 생각합니다.
    """
    sections = [{"heading": "요약", "columns": ["", "결과"],
                 "rows": capture_rows(result)}]
    if result.rows:
        sections.append(capture_holdings(result))
    return sections


def _max_drawdown(securities, histories: dict, rows: list, fx_hist,
                  cash_krw: float, buy_ts, final_ts) -> tuple[float, date | None]:
    """구간 중 고점 대비 최대 하락폭(%, 음수) 과 그 바닥 날짜.

    왜 이걸 계산하나
    ----------------
    백테스트는 "시작 -> 끝" 두 점만 봅니다. 그 사이에 -40% 를 지나왔더라도 결과에는
    안 나옵니다. **수익만 보여주면 앱이 아니라 광고가 됩니다.** 그 10년을 실제로
    버티려면 무엇을 견뎌야 했는지 같이 말해야 합니다.

    네트워크를 더 쓰지 않습니다
    ---------------------------
    필요한 일별 가격은 위에서 이미 다 받아놨습니다(histories, fx_hist).
    여기서는 그걸 다시 훑기만 합니다.

    분배금은 넣지 않습니다
    ----------------------
    "얼마나 빠졌나" 는 값이 내려간 폭을 뜻합니다. 중간에 받은 현금을 더하면 하락이
    실제보다 작아 보입니다. 보수적으로 **보유 자산 + 남은 현금** 만 봅니다.
    """
    by_id = {r.ticker: r for r in rows}
    frames = []
    for sec in securities:
        df = histories.get(sec.id)
        row = by_id.get(sec.ticker)
        if df is None or row is None or row.shares <= 0:
            continue
        s = df.loc[(df.index >= buy_ts) & (df.index <= final_ts), HISTORY_CLOSE_COL]
        if s.empty:
            continue
        frames.append((sec, row, s))
    if not frames:
        return 0.0, None

    # 나라마다 휴장일이 달라서 거래일이 어긋납니다. 교집합만 쓰면 표본이 뚝 떨어지므로,
    # 합집합에 각 종목의 **마지막으로 알려진 가격**을 채워서 평가합니다.
    index = frames[0][2].index
    for _, _, s in frames[1:]:
        index = index.union(s.index)
    if len(index) < 2:
        return 0.0, None

    total = pd.Series(float(cash_krw), index=index)
    fx_on_index = None
    if fx_hist is not None and len(fx_hist) > 0:
        fx_on_index = fx_hist.reindex(fx_hist.index.union(index)).ffill().reindex(index)

    for sec, row, s in frames:
        values = s.reindex(index).ffill() * float(row.shares)
        if sec.market == MARKET_US and sec.currency == "USD":
            if fx_on_index is None:
                return 0.0, None
            values = values * fx_on_index
        total = total.add(values.fillna(0.0), fill_value=0.0)

    total = total.dropna()
    if len(total) < 2:
        return 0.0, None
    drawdown = total / total.cummax() - 1.0
    worst = float(drawdown.min()) * 100.0
    if not math.isfinite(worst) or worst >= 0:
        return 0.0, None
    return worst, drawdown.idxmin().date()


@dataclass
class BacktestRow:
    ticker: str
    # 화면에 찍을 이름. 한국 종목은 티커가 종목코드(예: "458730")라서, 이게 없으면
    # 백테스트 표에 "TIGER 미국배당다우존스" 대신 "458730" 이 뜹니다(실제로 그랬습니다).
    display_name: str
    market: str
    currency: str
    target_weight: float
    buy_price_native: float       # 매수일 종가 (분할 소급반영된 계열)
    buy_fx: float | None          # 매수일 USD/KRW (KR 종목은 None)
    buy_price_krw: float
    shares: float                 # 매수 후 종료까지 그대로 보유 (리밸런싱/추가매수 없음)
    final_price_native: float      # 종료일 종가 (동일 계열)
    final_fx: float | None
    invested_krw: float
    final_value_krw: float
    distributions_cash_krw: float
    splits_in_period: int          # 구간 내 분할 발생 횟수 (정합성 참고, 계산에는 미반영)


@dataclass
class BacktestResult:
    ok: bool
    message: str = ""
    input_start: date | None = None
    # 상장이 늦은 종목 때문에 실패했을 때, "이 날짜로 바꾸면 된다" 는 날짜.
    # 메시지 안에 글자로만 적어두면 사용자가 직접 옮겨 적어야 해서, 화면이 버튼
    # 하나로 고쳐줄 수 있게 값으로도 내보냅니다 (사용자 요청).
    suggested_start: date | None = None
    actual_buy_date: date | None = None
    data_as_of: date | None = None
    initial_capital_krw: float = 0.0
    total_invested_krw: float = 0.0
    cash_balance_krw: float = 0.0
    distributions_cash_krw: float = 0.0
    final_value_krw: float = 0.0
    profit_krw: float = 0.0
    return_pct: float = 0.0
    # 구간 중 고점 대비 최대 하락폭(%, 음수). 0.0 이면 계산하지 못했다는 뜻입니다.
    # **수익률만 보여주면 앱이 아니라 광고가 됩니다.** 그 10년을 실제로 버티려면
    # 얼마나 빠지는 걸 견뎌야 했는지 같이 말해야 합니다.
    max_drawdown_pct: float = 0.0
    max_drawdown_date: date | None = None
    include_distributions: bool = False
    rows: list[BacktestRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    disclaimer: str = config.BACKTEST_DISCLAIMER

    @property
    def holdings_value_krw(self) -> float:
        """종료일 기준 **주식만** 의 평가액 (현금도 분배금도 뺀 값).

        final_value_krw 는 주식 + 남은 현금 + (켰다면) 받은 분배금을 **합친** 값입니다.
        "평가금액" 이라는 한 칸에 성격이 다른 셋을 뭉쳐 놓으면, 얼마가 주가로 번 것이고
        얼마가 통장에 쌓인 현금인지 알 수가 없습니다. 그래서 셋을 나눠서 보여줄 수
        있도록 주식 몫만 따로 꺼냅니다 (셋을 더하면 정확히 final_value_krw 입니다).
        """
        return sum(r.final_value_krw for r in self.rows)


def _load_price_history(sec: Security, start: date, end: date) -> pd.DataFrame:
    return get_provider(sec.market).get_price_history(sec.ticker, start, end)


def run_backtest(
    portfolio: Portfolio,
    start: date,
    *,
    initial_capital_krw: float | None = None,
    include_distributions: bool = False,
) -> BacktestResult:
    capital = float(initial_capital_krw if initial_capital_krw is not None
                    else portfolio.initial_capital_krw)
    fractional = bool(portfolio.fractional_shares)
    today = date.today()

    if not portfolio.securities:
        return BacktestResult(ok=False, message="백테스트할 종목이 없습니다.", input_start=start)
    if start >= today:
        return BacktestResult(ok=False, message="시작일은 오늘보다 이전이어야 합니다.",
                              input_start=start)

    wc = calc.check_total_weight([float(s.target_weight) for s in portfolio.securities],
                                 config.WEIGHT_SUM_EPSILON)
    if wc.is_over:
        return BacktestResult(ok=False, message=wc.message, input_start=start)

    warnings: list[str] = []

    # 1) 종목별 히스토리 로드 + 상장일 검증
    histories: dict[str, pd.DataFrame] = {}
    late_listed: list[str] = []
    latest_listing: date | None = None      # 늦게 상장한 종목들 중 가장 늦은 날 (안내용)
    for sec in portfolio.securities:
        try:
            df = _load_price_history(sec, start - timedelta(days=7), today)
        except DataUnavailable as e:
            return BacktestResult(ok=False, message=str(e), input_start=start)
        if df is None or df.empty:
            return BacktestResult(
                ok=False, input_start=start,
                message=f"[{sec.ticker}] 백테스트 구간의 가격 데이터가 없습니다.",
            )
        first_date = df.index.min().date()
        if first_date > start + timedelta(days=LISTING_TOLERANCE_DAYS):
            # 한국 종목은 티커가 종목코드라 그대로 쓰면 "458730" 만 보입니다.
            _name = sec.display_name if sec.market == MARKET_KR else sec.ticker
            late_listed.append(f"{_name}(데이터 시작 {first_date})")
            latest_listing = first_date if latest_listing is None else max(latest_listing, first_date)
        histories[sec.id] = df

    if late_listed:
        # 그냥 "안 된다"로 끝내면 사용자가 어느 날짜로 바꿔야 할지 직접 찾아야 합니다.
        # 전부 포함되는 가장 이른 날짜를 같이 알려줍니다 (상장이 늦은 종목 기준).
        return BacktestResult(
            ok=False, input_start=start, suggested_start=latest_listing,
            message=("백테스트 불가: 다음 종목은 시작일 이후에 상장되었습니다 -> "
                     + ", ".join(late_listed)
                     + (f" · 시작일을 {latest_listing} 이후로 잡으면 전부 포함됩니다."
                        if latest_listing else "")),
        )

    # 2) FX 히스토리 (미국 종목이 하나라도 있으면 필요)
    need_fx = any(s.market == MARKET_US and s.currency == "USD" for s in portfolio.securities)
    fx_hist: pd.Series | None = None
    if need_fx:
        try:
            fx_hist = fx_provider.get_history(start - timedelta(days=14), today)
        except DataUnavailable as e:
            return BacktestResult(ok=False, input_start=start,
                                  message=f"과거 USD/KRW 환율을 가져올 수 없습니다: {e}")

    # 3) 실제 매수 기준일 = 모든 종목(+FX) 이 데이터가 있는, 시작일 이후 첫 공통 거래일
    common_idx: pd.DatetimeIndex | None = None
    for df in histories.values():
        idx = df.index[df.index >= pd.Timestamp(start)]
        common_idx = idx if common_idx is None else common_idx.intersection(idx)
    if fx_hist is not None:
        fx_idx = fx_hist.index[fx_hist.index >= pd.Timestamp(start)]
        common_idx = fx_idx if common_idx is None else common_idx.intersection(fx_idx)
    if common_idx is None or len(common_idx) == 0:
        return BacktestResult(ok=False, input_start=start,
                              message="모든 종목이 공통으로 존재하는 거래일을 찾지 못했습니다.")
    buy_ts = common_idx.min()
    final_ts = common_idx.max()
    buy_date = buy_ts.date()
    data_as_of = final_ts.date()
    if buy_date != start:
        warnings.append(f"입력일 {start} 이(가) 거래일이 아니어서 {buy_date} 로 매수 기준일을 이동했습니다.")

    def fx_on(ts: pd.Timestamp) -> float:
        sub = fx_hist.loc[fx_hist.index <= ts]
        return float(sub.iloc[-1])

    # 4) 매수 / 평가
    rows: list[BacktestRow] = []
    total_invested = 0.0
    total_dist_cash = 0.0
    for sec in portfolio.securities:
        df = histories[sec.id]
        weight = float(sec.target_weight)
        target_amt = calc.calculate_target_amount(capital, weight)

        buy_price_native = float(df.loc[df.index <= buy_ts, HISTORY_CLOSE_COL].iloc[-1])
        final_price_native = float(df.loc[df.index <= final_ts, HISTORY_CLOSE_COL].iloc[-1])

        is_us = sec.market == MARKET_US and sec.currency == "USD"
        buy_fx = fx_on(buy_ts) if is_us else None
        final_fx = fx_on(final_ts) if is_us else None
        buy_price_krw = buy_price_native * buy_fx if is_us else buy_price_native
        if buy_price_krw <= 0:
            return BacktestResult(ok=False, input_start=start,
                                  message=f"[{sec.ticker}] 매수일 가격이 0 이하입니다.")

        if fractional:
            shares = calc.calculate_fractional_shares(target_amt, buy_price_krw)
        else:
            shares = calc.calculate_integer_shares(target_amt, buy_price_krw)
        invested = calc.calculate_actual_investment(shares, buy_price_krw)

        final_value_krw = (shares * final_price_native * final_fx) if is_us \
            else (shares * final_price_native)

        # 구간 내 분할 횟수 (정합성 참고용, 값 계산에는 미반영 -- 위 docstring 참조)
        splits_n = 0
        try:
            sp = get_provider(sec.market).get_splits(
                sec.ticker, buy_date + timedelta(days=1), data_as_of)
            splits_n = int(len(sp)) if sp is not None else 0
        except DataUnavailable:
            splits_n = 0

        # 분배금(옵션): 현금 수령, 재투자 없음. .dividends 도 분할 소급반영 계열이므로
        # (구간 내 주당 분배금 합계) x (보유수량) 이 그대로 성립.
        dist_cash = 0.0
        if include_distributions and shares > 0:
            dser = None
            _name = sec.display_name if sec.market == MARKET_KR else sec.ticker
            if sec.distribution_method == DIST_METHOD_MANUAL:
                # 상세 패널에서 **직접 입력한** 값은 "최근 12개월 주당 얼마" 라는 숫자
                # 하나입니다. 그걸 몇 년 구간에 펼치려면 언제 얼마씩 줬는지를 지어내야
                # 합니다. 지어내느니 빼고, 뺐다고 말합니다.
                warnings.append(
                    f"[{_name}] 분배금을 직접 입력하신 종목입니다. 입력값은 '최근 12개월' "
                    f"한 숫자라 과거 구간에 펼칠 수 없어, 백테스트 분배금에서 뺐습니다.")
            else:
                try:
                    dser = get_provider(sec.market).get_distributions(
                        sec.ticker, buy_date + timedelta(days=1), data_as_of)
                except DataUnavailable:
                    dser = None
                    warnings.append(
                        f"[{_name}] 분배금 데이터가 없어 백테스트 분배금 합산에서 제외했습니다.")
            if dser is not None and len(dser) > 0:
                if is_us:
                    for ts, per_share in dser.items():
                        dist_cash += float(per_share) * shares * fx_on(pd.Timestamp(ts))
                else:
                    dist_cash += float(dser.sum()) * shares

        total_dist_cash += dist_cash
        total_invested += invested
        rows.append(BacktestRow(
            ticker=sec.ticker, display_name=(sec.display_name or sec.name or sec.ticker),
            market=sec.market, currency=sec.currency, target_weight=weight,
            buy_price_native=buy_price_native, buy_fx=buy_fx, buy_price_krw=buy_price_krw,
            shares=shares, final_price_native=final_price_native, final_fx=final_fx,
            invested_krw=invested, final_value_krw=final_value_krw,
            distributions_cash_krw=dist_cash, splits_in_period=splits_n,
        ))

    cash_balance = calc.calculate_cash_balance(capital, total_invested)
    mdd_pct, mdd_date = _max_drawdown(
        portfolio.securities, histories, rows, fx_hist, cash_balance, buy_ts, final_ts)
    holdings_value = sum(r.final_value_krw for r in rows)
    final_value = holdings_value + cash_balance + (total_dist_cash if include_distributions else 0.0)
    profit = final_value - capital
    ret_pct = (profit / capital * 100.0) if capital > 0 else 0.0

    return BacktestResult(
        ok=True,
        input_start=start,
        actual_buy_date=buy_date,
        data_as_of=data_as_of,
        initial_capital_krw=capital,
        total_invested_krw=total_invested,
        cash_balance_krw=cash_balance,
        distributions_cash_krw=total_dist_cash,
        final_value_krw=final_value,
        profit_krw=profit,
        return_pct=ret_pct,
        max_drawdown_pct=mdd_pct,
        max_drawdown_date=mdd_date,
        include_distributions=include_distributions,
        rows=rows,
        warnings=warnings,
    )
