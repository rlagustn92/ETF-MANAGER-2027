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

from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

import config
from data.providers import fx_provider
from data.providers.base import DataUnavailable, HISTORY_CLOSE_COL
from data.providers.registry import get_provider
from models.portfolio import Portfolio
from models.security import MARKET_US, Security
from services import calculation_service as calc

# 시작일과 종목 데이터 시작일의 허용 격차(휴장/연휴). 이보다 크면 "상장 이후" 로 판단.
LISTING_TOLERANCE_DAYS = 10


@dataclass
class BacktestRow:
    ticker: str
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
    actual_buy_date: date | None = None
    data_as_of: date | None = None
    initial_capital_krw: float = 0.0
    total_invested_krw: float = 0.0
    cash_balance_krw: float = 0.0
    distributions_cash_krw: float = 0.0
    final_value_krw: float = 0.0
    profit_krw: float = 0.0
    return_pct: float = 0.0
    include_distributions: bool = False
    rows: list[BacktestRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    disclaimer: str = config.BACKTEST_DISCLAIMER


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
            late_listed.append(f"{sec.ticker}(데이터 시작 {first_date})")
            latest_listing = first_date if latest_listing is None else max(latest_listing, first_date)
        histories[sec.id] = df

    if late_listed:
        # 그냥 "안 된다"로 끝내면 사용자가 어느 날짜로 바꿔야 할지 직접 찾아야 합니다.
        # 전부 포함되는 가장 이른 날짜를 같이 알려줍니다 (상장이 늦은 종목 기준).
        return BacktestResult(
            ok=False, input_start=start,
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
            try:
                dser = get_provider(sec.market).get_distributions(
                    sec.ticker, buy_date + timedelta(days=1), data_as_of)
            except DataUnavailable:
                dser = None
                warnings.append(f"[{sec.ticker}] 분배금 데이터가 없어 백테스트 분배금 합산에서 제외했습니다.")
            if dser is not None and len(dser) > 0:
                if is_us:
                    for ts, per_share in dser.items():
                        dist_cash += float(per_share) * shares * fx_on(pd.Timestamp(ts))
                else:
                    dist_cash += float(dser.sum()) * shares

        total_dist_cash += dist_cash
        total_invested += invested
        rows.append(BacktestRow(
            ticker=sec.ticker, market=sec.market, currency=sec.currency, target_weight=weight,
            buy_price_native=buy_price_native, buy_fx=buy_fx, buy_price_krw=buy_price_krw,
            shares=shares, final_price_native=final_price_native, final_fx=final_fx,
            invested_krw=invested, final_value_krw=final_value_krw,
            distributions_cash_krw=dist_cash, splits_in_period=splits_n,
        ))

    cash_balance = calc.calculate_cash_balance(capital, total_invested)
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
        include_distributions=include_distributions,
        rows=rows,
        warnings=warnings,
    )
