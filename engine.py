from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import pytz

# --------- Constants
AED, EUR, USD = "AED", "EUR", "USD"

ACQ_DATE: date = date(2024, 9, 30)
ACQ_PRICE: float = 11_800_000.0

TARGET_DATE: date = date(2028, 5, 30)
TARGET_PRICE: float = 17_500_000.0

AED_PER_USD: float = 3.6727
AED_PER_EUR: float = 4.31371  # this should be read live from online source?

CURRENCY_RATES = {
    AED: 1.0,
    USD: 1.0 / AED_PER_USD,
    EUR: 1.0 / AED_PER_EUR,
}

INVESTMENT_DATES: List[date] = [
    date(2024, 9, 30),
    date(2025, 1, 31),
    date(2025, 9, 30),
    date(2026, 5, 30),
    date(2027, 1, 30),
    date(2027, 9, 30),
    date(2028, 5, 30),
    date(2028, 9, 30),
]

EDITABLE_START: date = date(2025, 9, 30)

ALDAR_PLAN: Dict[date, float] = {
    date(2024, 9, 30): 1_188_000.0,
    date(2025, 1, 31): 1_188_000.0,
    date(2025, 9, 30): 1_188_000.0,
    date(2026, 5, 30): 1_782_000.0,
    date(2027, 1, 30): 1_188_000.0,
    date(2027, 9, 30): 1_188_000.0,
    date(2028, 5, 30): 4_158_000.0,
}

DEFAULT_ANTOINE: Dict[date, float] = {
    date(2024, 9, 30): 1_188_000.0,
    date(2025, 1, 31): 1_188_000.0,
}

DUBAI_TZ = pytz.timezone("Asia/Dubai")
TODAY = datetime.now(DUBAI_TZ).date()

EXIT_RATE_CUTOFF = date(
    2028, 9, 30
)  # if sell or exit on or after this date then 20 p.a., else 15 p.a.


# --------- Helpers
def make_daily_index(start: date, end: date) -> pd.DatetimeIndex:
    return pd.date_range(start=start, end=end, freq="D")


def linear_price_series(
    acq_date: date, acq_price: float, target_date: date, target_price: float
) -> pd.Series:
    idx = make_daily_index(acq_date, target_date)
    if len(idx) <= 1:
        return pd.Series([acq_price], index=pd.to_datetime([acq_date]), name="price")
    step = (target_price - acq_price) / (len(idx) - 1)
    vals = [acq_price + i * step for i in range(len(idx))]
    s = pd.Series(vals, index=idx, name="price")
    return s


def base_contrib_df(investment_dates: List[date]) -> pd.DataFrame:
    df = pd.DataFrame(index=pd.to_datetime(investment_dates))
    df.index.name = "date"
    for col in ["Antoine", "New investor", "Total plan"]:
        df[col] = 0.0
    return df


def build_daily_invested(
    contrib_df: pd.DataFrame, acq_date: date, end_date: date
) -> pd.DataFrame:
    df = contrib_df.copy()
    residual = (df["Total plan"] - df["Antoine"] - df["New investor"]).clip(lower=0.0)
    df["Other investors"] = residual
    idx_daily = make_daily_index(acq_date, end_date)
    daily = pd.DataFrame(index=idx_daily)
    for col in ["Antoine", "New investor", "Other investors"]:
        daily[col] = df[col].reindex(idx_daily, method=None).fillna(0.0).cumsum()
    daily["Total"] = daily[["Antoine", "New investor", "Other investors"]].sum(axis=1)
    return daily


@dataclass
class GainBreakdown:
    appreciation: float
    guarantee: float
    final: float


def _ensure_on_series(ps: pd.Series, d: date, acq_date: date) -> pd.Series:
    if pd.Timestamp(d) in ps.index:
        return ps
    full_idx = pd.DatetimeIndex(
        sorted(set(ps.index.tolist() + [pd.Timestamp(d), pd.Timestamp(acq_date)]))
    )
    return ps.reindex(full_idx).interpolate(method="time").ffill().bfill()


def gains_at_date(
    when: date,
    acq_date: date,
    acq_price: float,
    price_series: pd.Series,
    daily_invested: pd.DataFrame,
    contrib_df: pd.DataFrame = None,
) -> Dict[str, GainBreakdown]:
    # Sale case: Others get max(appreciation-based, 15 p.a.). Antoine gets residual of project appreciation.
    if when <= acq_date:
        zero = GainBreakdown(0.0, 0.0, 0.0)
        return {"Antoine": zero, "New investor": zero, "Other investors": zero}

    ps = _ensure_on_series(price_series.copy().sort_index(), when, acq_date)
    price_t = float(ps.loc[pd.Timestamp(when)])
    total_appreciation = max(price_t - acq_price, 0.0)

    start = acq_date + timedelta(days=1)
    idx = make_daily_index(start, when)
    inv = daily_invested.reindex(idx).ffill().fillna(0.0)

    total_days = max((when - acq_date).days, 1)
    daily_app = total_appreciation / total_days

    shares = pd.DataFrame(index=idx)
    for col in ["Antoine", "New investor", "Other investors"]:
        shares[col] = inv[col] / inv["Total"].replace(0.0, np.nan)
    shares = shares.fillna(0.0)

    appreciation = shares.sum(axis=0) * daily_app

    # Calculate guarantee using per-investment-date method if contrib_df is provided
    if contrib_df is not None:
        guarantee_dict = per_part_guarantee_by_investment_date(when, contrib_df, 0.15)
        guarantee_raw = pd.Series(guarantee_dict)
    else:
        # Fallback to old method if contrib_df not provided
        days_invested = max((when - acq_date).days, 1)
        annual_rate_factor = 0.15 * (days_invested / 365.0)
        final_invested = inv.iloc[-1][["Antoine", "New investor", "Other investors"]]
        guarantee_raw = final_invested * annual_rate_factor

    result: Dict[str, GainBreakdown] = {}
    others = ["New investor", "Other investors"]
    others_sum = 0.0
    for k in others:
        app = float(appreciation[k])
        gte = float(guarantee_raw[k])
        final = max(app, gte)
        others_sum += final
        result[k] = GainBreakdown(appreciation=app, guarantee=gte, final=final)

    ant_app = float(appreciation["Antoine"])
    ant_final = total_appreciation - others_sum
    result["Antoine"] = GainBreakdown(
        appreciation=ant_app, guarantee=0.0, final=ant_final
    )
    return result


def per_part_guarantee_by_investment_date(
    when: date, contrib_df: pd.DataFrame, rate_annual: float
) -> Dict[str, float]:
    """Calculate guarantee based on individual investment dates and periods."""
    if when <= contrib_df.index.min().date():
        return {"Antoine": 0.0, "New investor": 0.0, "Other investors": 0.0}

    result = {"Antoine": 0.0, "New investor": 0.0, "Other investors": 0.0}

    # Calculate "Other investors" column if it doesn't exist
    df = contrib_df.copy()
    if "Other investors" not in df.columns:
        residual = (df["Total plan"] - df["Antoine"] - df["New investor"]).clip(
            lower=0.0
        )
        df["Other investors"] = residual

    # Calculate guarantee for each investment date
    for investment_date in df.index:
        inv_date = investment_date.date()
        if inv_date >= when:
            continue  # Investment is after the check date

        # Calculate days from investment to check date
        days_invested = max((when - inv_date).days, 1)
        annual_rate_factor = rate_annual * (days_invested / 365.0)

        # Add guarantee for this investment
        for col in ["Antoine", "New investor", "Other investors"]:
            investment_amount = df.loc[investment_date, col]
            guarantee = investment_amount * annual_rate_factor
            result[col] += guarantee

    return result


def per_part_guarantee(
    when: date, acq_date: date, daily_invested: pd.DataFrame, rate_annual: float
) -> Dict[str, float]:
    if when <= acq_date:
        return {"Antoine": 0.0, "New investor": 0.0, "Other investors": 0.0}
    start = acq_date + timedelta(days=1)
    idx = make_daily_index(start, when)
    inv = daily_invested.reindex(idx).ffill().fillna(0.0)
    # Calculate guarantee based on annual rate and time period
    days_invested = max((when - acq_date).days, 1)
    annual_rate_factor = rate_annual * (days_invested / 365.0)

    # Use the final values (not cumulative sum) for guarantee calculation
    final_invested = inv.iloc[-1][["Antoine", "New investor", "Other investors"]]

    g = final_invested * annual_rate_factor
    return {k: float(v) for k, v in g.to_dict().items()}


def exit_gains_at_date(
    when: date,
    acq_date: date,
    acq_price: float,
    price_series: pd.Series,
    daily_invested: pd.DataFrame,
    contrib_df: pd.DataFrame = None,
) -> Tuple[Dict[str, float], float]:
    ps = _ensure_on_series(price_series.copy().sort_index(), when, acq_date)
    price_t = float(ps.loc[pd.Timestamp(when)])
    total_appreciation = max(price_t - acq_price, 0.0)
    rate_annual = 0.20 if when >= EXIT_RATE_CUTOFF else 0.15

    # Use the new calculation method if contrib_df is provided
    if contrib_df is not None:
        g = per_part_guarantee_by_investment_date(when, contrib_df, rate_annual)
    else:
        g = per_part_guarantee(when, acq_date, daily_invested, rate_annual=rate_annual)

    others_sum = g["New investor"] + g["Other investors"]
    ant_residual = total_appreciation - others_sum
    return {
        "Antoine": ant_residual,
        "New investor": g["New investor"],
        "Other investors": g["Other investors"],
    }, rate_annual


def get_daily_gain_per_dollar(
    when: date,
    acq_date: date,
    acq_price: float,
    price_series: pd.Series,
    daily_invested: pd.DataFrame,
) -> float:
    """
    Calculate the daily appreciation gain per dollar at a given time.

    This changes over time because:
    - The total appreciation is divided by the total days from acquisition
    - That daily amount is then divided by the total investment at that time

    Args:
        when: The date to calculate the gain for
        acq_date: Acquisition date of the property
        acq_price: Acquisition price
        price_series: Series of property prices over time
        daily_invested: DataFrame with total invested amounts per day

    Returns:
        The daily gain per dollar invested at that time
    """
    if when <= acq_date:
        return 0.0

    # Get the current price
    ps = _ensure_on_series(price_series.copy().sort_index(), when, acq_date)
    price_t = float(ps.loc[pd.Timestamp(when)])
    total_appreciation = max(price_t - acq_price, 0.0)

    # Calculate total days from acquisition
    total_days = max((when - acq_date).days, 1)

    # Daily appreciation for the entire project
    daily_app = total_appreciation / total_days

    # Get total invested at this date
    start = acq_date + timedelta(days=1)
    idx = make_daily_index(start, when)
    inv = daily_invested.reindex(idx).ffill().fillna(0.0)
    total_invested_at_time = inv["Total"].iloc[-1]

    # If there's no investment yet, return 0
    if total_invested_at_time <= 0:
        return 0.0

    # Daily gain per dollar = total daily appreciation / total invested
    daily_gain_per_dollar = daily_app / total_invested_at_time

    return daily_gain_per_dollar
