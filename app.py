# app.py
# Oasis Co-Investor Portal (Option A – simple, no auth; Streamlit-first with safe fallback)
# -------------------------------------------------------------------------------------------------
# Streamlit app for co-investors:
# - Fixed investment windows (provided by Antoine)
# - Participants: "Antoine", "New investor"; "Other investors" is residual from fixed Total plan (Aldar installments)
# - Price path: linear target in the sidebar, or CSV upload (date,price)
# - Gains TODAY and at a chosen date (SALE case)
#   • Other investors receive max(Appreciation-based, Guaranteed 15% p.a.)
#   • Antoine receives the RESIDUAL: total project appreciation − payouts to other investors (no guarantee)
# - EXIT case (guarantee rate depends on date):
#   • If when ≤ 2028-09-30: Others receive 15% p.a. guarantee (time-weighted)
#   • If when  > 2028-09-30: Others receive 20% p.a. guarantee (time-weighted)
#   • Antoine receives the RESIDUAL of the *total project appreciation* after others' guarantees
# - Visualizations for invested balances and gains tables
#
# Assumptions:
# - Contributions are effective ON their date (inclusive).
# - Daily accumulation window is from the day AFTER acquisition up to and including the evaluation date.
# - Guaranteed r% p.a. = sum_over_days(invested_balance * r/365). (Actual/365 simple daily accrual.)
# - Share(d) = invested_i(d)/total_invested(d); if total=0, share=0 for all.
# - Currency: AED; Timezone: Asia/Dubai.

from __future__ import annotations
import os
import sys
from dataclasses import dataclass
from typing import Dict, List, Tuple
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
import pytz

# -------------------- Try importing Streamlit --------------------
STREAMLIT_AVAILABLE = True
try:
    import streamlit as st
except Exception:
    STREAMLIT_AVAILABLE = False

# -------------------- Try importing Altair for rich charts --------------------
ALT_AVAILABLE = True
try:
    import altair as alt
except Exception:
    ALT_AVAILABLE = False

# -------------------- Constants & Defaults --------------------
AED = "AED"
# Hard-coded acquisition details
ACQ_DATE: date = date(2024, 9, 30)
ACQ_PRICE: float = 11_800_000.0
# Hard-coded projection target
TARGET_DATE: date = date(2028, 5, 30)
TARGET_PRICE: float = 20_000_000.0
# FX peg for USD conversion (AED per USD)
AED_PER_USD: float = 3.6725

INVESTMENT_DATES: List[date] = [
    date(2024, 9, 30),  # 1st
    date(2025, 1, 31),  # 2nd
    date(2025, 9, 30),  # 3rd
    date(2026, 5, 30),  # 4th ← default scenario date
    date(2027, 1, 30),
    date(2027, 9, 30),
    date(2028, 5, 30),
]

# Editable contribution inputs start at this window
EDITABLE_START: date = date(2025, 9, 30)

# Fixed Aldar installment plan (read-only in UI)
ALDAR_PLAN: Dict[date, float] = {
    date(2024, 9, 30): 1_188_000.0,
    date(2025, 1, 31): 1_188_000.0,
    date(2025, 9, 30): 1_188_000.0,
    date(2026, 5, 30): 1_782_000.0,  # special
    date(2027, 1, 30): 1_188_000.0,
    date(2027, 9, 30): 1_188_000.0,
    date(2028, 5, 30): 4_158_000.0,  # special
}

# Defaults: past contributions for Antoine
DEFAULT_ANTOINE: Dict[date, float] = {
    date(2024, 9, 30): 1_188_000.0,
    date(2025, 1, 31): 1_188_000.0,
}

DUBAI_TZ = pytz.timezone("Asia/Dubai")
TODAY = datetime.now(DUBAI_TZ).date()

# EXIT rate rule
EXIT_RATE_CUTOFF = date(2028, 9, 30)  # if when > this date => 20% p.a., else 15% p.a.

# -------------------- Core helpers (streamlit-agnostic) --------------------

def fmt_aed(x: float) -> str:
    try:
        return f"{x:,.0f} {AED}"
    except Exception:
        return f"{x} {AED}"

def fmt_usd(x: float) -> str:
    try:
        return f"${x:,.0f}"
    except Exception:
        return f"${x}"

def make_daily_index(start: date, end: date) -> pd.DatetimeIndex:
    return pd.date_range(start=start, end=end, freq="D")

def base_contrib_df(investment_dates: List[date]) -> pd.DataFrame:
    df = pd.DataFrame(index=pd.to_datetime(investment_dates))
    df.index.name = "date"
    for col in ["Antoine", "New investor", "Total plan"]:
        df[col] = 0.0
    return df

def default_total_plan_from(df_contrib: pd.DataFrame) -> pd.Series:
    return (df_contrib["Antoine"] + df_contrib["New investor"]).astype(float)

def linear_price_series(acq_date: date, acq_price: float, target_date: date, target_price: float) -> pd.Series:
    idx = make_daily_index(acq_date, target_date)
    n = len(idx) - 1
    if n <= 0:
        s = pd.Series([float(acq_price)], index=pd.to_datetime([acq_date]))
        s.name = "price"
        return s
    step = (target_price - acq_price) / n
    values = [acq_price + i * step for i in range(n + 1)]
    s = pd.Series(values, index=idx)
    s.name = "price"
    return s

def parse_price_csv(file) -> pd.Series:
    df = pd.read_csv(file)
    cols = {c.lower() for c in df.columns}
    if not {"date", "price"}.issubset(cols):
        raise ValueError("CSV must have 'date' and 'price' columns")
    df.columns = [c.lower() for c in df.columns]
    s = pd.Series(df["price"].values, index=pd.to_datetime(df["date"]))
    s = s.sort_index()
    s.name = "price"
    return s

def build_daily_invested(contrib_df: pd.DataFrame, acq_date: date, end_date: date) -> pd.DataFrame:
    """From per-window contributions to daily invested balances per participant."""
    df = contrib_df.copy()
    residual = (df["Total plan"] - df["Antoine"] - df["New investor"]).clip(lower=0.0)
    df["Other investors"] = residual

    idx_daily = make_daily_index(acq_date, end_date)
    daily = pd.DataFrame(index=idx_daily)
    for col in ["Antoine", "New investor", "Other investors"]:
        series = df[col].reindex(daily.index, method=None).fillna(0.0)
        daily[col] = series.cumsum()
    daily["Total"] = daily[["Antoine", "New investor", "Other investors"]].sum(axis=1)
    return daily

@dataclass
class GainBreakdown:
    appreciation: float
    guarantee: float
    final: float

def gains_at_date(
    when: date,
    acq_date: date,
    acq_price: float,
    price_series: pd.Series,
    daily_invested: pd.DataFrame,
) -> Dict[str, GainBreakdown]:
    """
    SALE case at 'when':
      - Others' payout = max(appreciation_share, guarantee15)
      - Antoine payout = residual of total project appreciation (no guarantee)
    """
    start = acq_date + timedelta(days=1)
    if when <= acq_date:
        zero = GainBreakdown(0.0, 0.0, 0.0)
        return {"Antoine": zero, "New investor": zero, "Other investors": zero}

    idx = make_daily_index(start, when)

    # Ensure price series covers 'when'
    ps = price_series.copy().sort_index()
    if pd.Timestamp(when) not in ps.index:
        full_idx = pd.DatetimeIndex(sorted(set(ps.index.tolist() + [pd.Timestamp(when), pd.Timestamp(acq_date)])))
        ps = ps.reindex(full_idx).interpolate(method="time").ffill().bfill()

    price_t = float(ps.loc[pd.Timestamp(when)])

    total_days = (when - acq_date).days
    total_appreciation = max(price_t - acq_price, 0.0)
    daily_appreciation = (total_appreciation / total_days) if total_days > 0 else 0.0

    inv = daily_invested.reindex(idx).ffill().fillna(0.0)
    total_invested = inv["Total"].replace(0.0, np.nan)

    shares = pd.DataFrame(index=idx)
    for col in ["Antoine", "New investor", "Other investors"]:
        shares[col] = inv[col] / total_invested
    shares = shares.fillna(0.0)

    appreciation = shares.sum(axis=0) * daily_appreciation

    rate_daily_15 = 0.15 / 365.0
    guarantee_raw = inv[["Antoine", "New investor", "Other investors"]].sum(axis=0) * rate_daily_15

    out: Dict[str, GainBreakdown] = {}
    others = ["New investor", "Other investors"]
    others_payout_sum = 0.0
    for col in others:
        app = float(appreciation[col])
        gte = float(guarantee_raw[col])
        final = max(app, gte)
        others_payout_sum += final
        out[col] = GainBreakdown(appreciation=app, guarantee=gte, final=final)

    ant_app = float(appreciation["Antoine"])
    ant_final = total_appreciation - others_payout_sum
    out["Antoine"] = GainBreakdown(appreciation=ant_app, guarantee=0.0, final=ant_final)

    return out

def per_part_guarantee(
    when: date,
    acq_date: date,
    daily_invested: pd.DataFrame,
    rate_annual: float,
) -> Dict[str, float]:
    """Time-weighted guarantee per participant at rate_annual."""
    start = acq_date + timedelta(days=1)
    if when <= acq_date:
        return {"Antoine": 0.0, "New investor": 0.0, "Other investors": 0.0}
    idx = make_daily_index(start, when)
    inv = daily_invested.reindex(idx).ffill().fillna(0.0)
    rate_daily = rate_annual / 365.0
    g = inv[["Antoine", "New investor", "Other investors"]].sum(axis=0) * rate_daily
    return {k: float(v) for k, v in g.to_dict().items()}

def exit_gains_at_date(
    when: date,
    acq_date: date,
    acq_price: float,
    price_series: pd.Series,
    daily_invested: pd.DataFrame,
) -> Tuple[Dict[str, float], float]:
    """
    EXIT case at 'when':
      - Others' guarantee rate is 15% p.a. if when <= 2028-09-30; otherwise 20% p.a.
      - Final payouts:
          * New investor, Other investors: their guarantee at the applicable rate
          * Antoine: residual of total project appreciation
      - Returns (payouts_dict, rate_used)
    """
    # Ensure price covers 'when'
    ps = price_series.copy().sort_index()
    if pd.Timestamp(when) not in ps.index:
        full_idx = pd.DatetimeIndex(sorted(set(ps.index.tolist() + [pd.Timestamp(when), pd.Timestamp(acq_date)])))
        ps = ps.reindex(full_idx).interpolate(method="time").ffill().bfill()
    price_t = float(ps.loc[pd.Timestamp(when)])
    total_appreciation = max(price_t - acq_price, 0.0)

    # Pick rate by rule
    rate_annual = 0.20 if when > EXIT_RATE_CUTOFF else 0.15

    # Guarantees at chosen rate
    g = per_part_guarantee(when, acq_date, daily_invested, rate_annual=rate_annual)
    others_sum = g["New investor"] + g["Other investors"]

    # Antoine residual (can be negative)
    ant_residual = total_appreciation - others_sum

    return (
        {
            "Antoine": ant_residual,
            "New investor": g["New investor"],
            "Other investors": g["Other investors"],
        },
        rate_annual,
    )

# -------------------- Streamlit UI --------------------

def run_streamlit_app():
    st.set_page_config(page_title="Oasis Co-Investor Simulator", page_icon="🏗️", layout="wide")

    # Sidebar
    st.sidebar.title("⚙️ Configuration")
    st.sidebar.info(f"Acquisition: {ACQ_DATE.isoformat()} | {fmt_aed(ACQ_PRICE)} (fixed)")

    st.sidebar.markdown("---")
    st.sidebar.info(f"Projection target (fixed): {TARGET_DATE.isoformat()} → {fmt_aed(TARGET_PRICE)}")
    price_series = linear_price_series(ACQ_DATE, ACQ_PRICE, TARGET_DATE, TARGET_PRICE)

    st.sidebar.markdown("---")
    selected_participant = st.sidebar.selectbox("Participant to view", ["Antoine", "Other investors", "New investor"], index=0)

    # Default to the 4th installment date
    default_scenario_date = INVESTMENT_DATES[3]
    sell_date = st.sidebar.date_input("Scenario: sell / withdraw date", value=default_scenario_date)
    st.sidebar.caption("Daily indices are computed in Asia/Dubai time. Gains today use today's Dubai date.")

    # Main
    st.title("🏗️ Oasis Co-Investor Simulator")
    st.caption("Option A - simple, no login. Define contributions, choose a price path, and evaluate gains.")
    
    # --- Top metrics placeholder (renders above contributions) ---
    metrics_box = st.container()

    st.subheader("1) Investment windows & contributions")
    contrib_df = base_contrib_df(INVESTMENT_DATES).copy()
    for d, v in DEFAULT_ANTOINE.items():
        if d in contrib_df.index.date:
            contrib_df.loc[pd.Timestamp(d), "Antoine"] = v

    with st.expander("Edit contributions per window", expanded=True):
        if selected_participant == "New investor":
            # Show ONLY New investor contributions editor + Aldar plan
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**New investor (guest)**")
                st.caption("Windows before 2025-09-30 are fixed and hidden.")
                for d in [d for d in INVESTMENT_DATES if d >= EDITABLE_START]:
                    key = f"new_{d.isoformat()}"
                    val = st.number_input(f"{d.isoformat()} ", value=float(contrib_df.loc[pd.Timestamp(d), "New investor"]), step=50000.0, format="%0.0f", key=key)
                    contrib_df.loc[pd.Timestamp(d), "New investor"] = val
            with c2:
                st.markdown("**Aldar installment plan (fixed)**")
                _plan_df = pd.DataFrame({
                    "date": [d.strftime("%Y-%m-%d") for d in INVESTMENT_DATES],
                    "installment": [ALDAR_PLAN.get(d, 0.0) for d in INVESTMENT_DATES],
                }).set_index("date")
                st.dataframe(_plan_df.style.format({"installment": "{:,.0f}"}), use_container_width=True)
        else:
            # Show ALL contributions editors when Antoine or Other investors is selected
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown("**Antoine**")
                st.caption("Windows before 2025-09-30 are fixed and hidden.")
                for d in [d for d in INVESTMENT_DATES if d >= EDITABLE_START]:
                    key = f"antoine_{d.isoformat()}"
                    val = st.number_input(f"{d.isoformat()}", value=float(contrib_df.loc[pd.Timestamp(d), "Antoine"]), step=50000.0, format="%0.0f", key=key)
                    contrib_df.loc[pd.Timestamp(d), "Antoine"] = val
            with c2:
                st.markdown("**New investor (guest)**")
                st.caption("Windows before 2025-09-30 are fixed and hidden.")
                for d in [d for d in INVESTMENT_DATES if d >= EDITABLE_START]:
                    key = f"new_{d.isoformat()}"
                    val = st.number_input(f"{d.isoformat()} ", value=float(contrib_df.loc[pd.Timestamp(d), "New investor"]), step=50000.0, format="%0.0f", key=key)
                    contrib_df.loc[pd.Timestamp(d), "New investor"] = val
            with c3:
                st.markdown("**Aldar installment plan (fixed)**")
                _plan_df = pd.DataFrame({
                    "date": [d.strftime("%Y-%m-%d") for d in INVESTMENT_DATES],
                    "installment": [ALDAR_PLAN.get(d, 0.0) for d in INVESTMENT_DATES],
                }).set_index("date")
                st.dataframe(_plan_df.style.format({"installment": "{:,.0f}"}), use_container_width=True)

    # Apply fixed Aldar plan to Total plan
    contrib_df["Total plan"] = 0.0
    for d in INVESTMENT_DATES:
        contrib_df.loc[pd.Timestamp(d), "Total plan"] = ALDAR_PLAN.get(d, 0.0)

    # Warn if plan < Antoine + New (residual clipped to 0)
    over_by = (contrib_df["Antoine"] + contrib_df["New investor"]) - contrib_df["Total plan"]
    if (over_by > 0).any():
        bad_dates = [d.date().isoformat() for d in contrib_df.index[over_by > 0]]
        st.warning("On some windows, Antoine + New exceed the Aldar plan. Residual set to 0 for: " + ", ".join(bad_dates))

    # Conditionally show columns in the contributions table
    contrib_view = contrib_df.copy()
    contrib_view.index = contrib_view.index.strftime("%Y-%m-%d")
    if selected_participant == "New investor":
        cols_to_show = ["New investor", "Total plan"]
    else:
        cols_to_show = ["Antoine", "New investor", "Total plan"]
    fmt_map = {col: "{:,.0f}" for col in cols_to_show}
    st.dataframe(contrib_view[cols_to_show].style.format(fmt_map), use_container_width=True)

    # Daily invested balances
    end_for_invested = max(sell_date, TODAY, price_series.index.max().date() if len(price_series) else ACQ_DATE)
    daily_invested = build_daily_invested(contrib_df, ACQ_DATE, end_for_invested)

    st.subheader("2) Invested balances (daily)")

    # ---- Altair charts (nice monthly ticks) ----
    import importlib
    global ALT_AVAILABLE
    try:
        alt = importlib.import_module("altair")
        ALT_AVAILABLE = True
    except Exception:
        ALT_AVAILABLE = False

    def _bimonth_ticks(start_ts: pd.Timestamp, end_ts: pd.Timestamp):
        start_month = pd.Timestamp(start_ts).normalize().replace(day=1)
        end_month = pd.Timestamp(end_ts).normalize().replace(day=1)
        months = pd.date_range(start_month, end_month, freq="2MS")
        if ALT_AVAILABLE:
            return [alt.DateTime(year=m.year, month=m.month) for m in months]
        else:
            return [pd.Timestamp(m) for m in months]

    di_start, di_end = pd.Timestamp(daily_invested.index.min()), pd.Timestamp(daily_invested.index.max())
    di_ticks = _bimonth_ticks(di_start, di_end)

    # 1) All participants – invested amount (daily) (Antoine only)
    if selected_participant == "Antoine":
        if ALT_AVAILABLE:
            df_all = daily_invested.reset_index().rename(columns={"index": "date"})
            chart_all = alt.Chart(df_all).transform_fold(
                ["Antoine", "New investor", "Other investors"], as_=["participant", "value"]
            ).mark_line().encode(
                x=alt.X("date:T", axis=alt.Axis(format="%b %Y", labelAngle=0, values=di_ticks)),
                y=alt.Y("value:Q", title="Invested (AED)"),
                color=alt.Color("participant:N", legend=alt.Legend(title="Participant"))
            ).properties(height=300)
            st.altair_chart(chart_all, use_container_width=True)
        else:
            st.markdown("**All participants – invested amount (daily)**")
            st.line_chart(daily_invested[["Antoine", "New investor", "Other investors"]])

        st.markdown("**Unit price over time (projection)**")
        show_usd = st.checkbox("Show price in USD", value=False, help="Convert from AED at fixed 3.6725")
        series = price_series.sort_index()
        series = pd.to_numeric(series, errors="coerce")
        if show_usd:
            series = series / AED_PER_USD
            y_title = "Price (USD)"
            acq_p = ACQ_PRICE / AED_PER_USD
            tgt_p = TARGET_PRICE / AED_PER_USD
        else:
            y_title = "Price (AED)"
            acq_p = ACQ_PRICE
            tgt_p = TARGET_PRICE
        df_price = series.reset_index()
        df_price.columns = ["date", "price"]
        df_price = df_price.dropna(subset=["price"]).reset_index(drop=True)

        ps_start, ps_end = pd.Timestamp(df_price["date"].min()), pd.Timestamp(df_price["date"].max())
        ps_ticks = _bimonth_ticks(ps_start, ps_end)

        if ALT_AVAILABLE and not df_price.empty:
            line = alt.Chart(df_price).mark_line().encode(
                x=alt.X("date:T", axis=alt.Axis(format="%b %Y", labelAngle=0, values=ps_ticks)),
                y=alt.Y("price:Q", title=y_title)
            ).properties(height=300)
            rule_acq = alt.Chart(pd.DataFrame({"date": [pd.Timestamp(ACQ_DATE)]})).mark_rule(strokeDash=[4,4]).encode(x="date:T")
            rule_tgt = alt.Chart(pd.DataFrame({"date": [pd.Timestamp(TARGET_DATE)]})).mark_rule(strokeDash=[4,4]).encode(x="date:T")
            markers_df = pd.DataFrame({
                "date": [pd.Timestamp(ACQ_DATE), pd.Timestamp(TARGET_DATE)],
                "price": [acq_p, tgt_p],
                "label": ["Acquisition", "Target"],
            })
            pts = alt.Chart(markers_df).mark_point(filled=True, size=80).encode(
                x="date:T", y="price:Q", shape="label:N", tooltip=["label", "date:T", "price:Q"]
            )
            txt = alt.Chart(markers_df).mark_text(align="left", dx=5, dy=-5).encode(
                x="date:T", y="price:Q", text="label"
            )
            st.altair_chart(line + rule_acq + rule_tgt + pts + txt, use_container_width=True)
        else:
            st.line_chart(df_price.set_index("date")["price"].to_frame(name=y_title))

    # 2) Selected participant – invested amount (daily)
    if ALT_AVAILABLE:
        df_sel = daily_invested.reset_index().rename(columns={"index": "date"})
        line_sel = alt.Chart(df_sel).mark_line().encode(
            x=alt.X("date:T", axis=alt.Axis(format="%b %Y", labelAngle=0, values=di_ticks)),
            y=alt.Y(f"{selected_participant}:Q", title="Invested (AED)")
        ).properties(height=300)
        st.altair_chart(line_sel, use_container_width=True)
    else:
        st.markdown(f"**{selected_participant} – invested amount (daily)**")
        st.line_chart(daily_invested[[selected_participant]])

    # 3) Selected participant – share of total (daily)
    share_series = (daily_invested[selected_participant] / daily_invested["Total"]).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    if ALT_AVAILABLE:
        share_df = share_series.reset_index()
        share_df.columns = ["date", "share"]
        line_sh = alt.Chart(share_df).mark_line().encode(
            x=alt.X("date:T", axis=alt.Axis(format="%b %Y", labelAngle=0, values=di_ticks)),
            y=alt.Y("share:Q", title="Share of total", scale=alt.Scale(domain=[0,1]), axis=alt.Axis(format='%'))
        ).properties(height=300)
        st.altair_chart(line_sh, use_container_width=True)
    else:
        st.markdown(f"**{selected_participant} – share of total investment (daily)**")
        st.line_chart(share_series)

    # Ensure price covers today and sell_date
    min_needed_end = max(TODAY, sell_date)
    if price_series.index.max().date() < min_needed_end:
        last_date = price_series.index.max().date()
        last_price = float(price_series.iloc[-1])
        ext_idx = make_daily_index(last_date, min_needed_end)
        add = pd.Series(last_price, index=ext_idx)
        price_series = pd.concat([price_series, add[1:]])

    # ---- Compute gains: Today (SALE), At sell_date (SALE), and At sell_date (EXIT with 15%/20%) ----
    results_today   = gains_at_date(TODAY,      ACQ_DATE, ACQ_PRICE, price_series, daily_invested)        # SALE (Antoine residual)
    results_sell    = gains_at_date(sell_date,  ACQ_DATE, ACQ_PRICE, price_series, daily_invested)        # SALE (Antoine residual)
    results_exit, exit_rate = exit_gains_at_date(sell_date, ACQ_DATE, ACQ_PRICE, price_series, daily_invested)  # EXIT (residual)

    # For display: others' guarantee numbers at the exit rate
    g_display = per_part_guarantee(sell_date, ACQ_DATE, daily_invested, exit_rate)
    exit_rate_label = f"{int(round(exit_rate*100))}%"

    parts = ["Antoine", "New investor", "Other investors"]
    summary_today = pd.DataFrame({
        p: {
            "Appreciation-based": results_today[p].appreciation,
            "Guaranteed (15% p.a.)": (0.0 if p == "Antoine" else results_today[p].guarantee),
            "Final (max/residual)": results_today[p].final,
        } for p in parts
    }).T

    summary_sell = pd.DataFrame({
        p: {
            "Appreciation-based": results_sell[p].appreciation,
            "Guaranteed (15% p.a.)": (0.0 if p == "Antoine" else results_sell[p].guarantee),
            "Final (max/residual)": results_sell[p].final,
        } for p in parts
    }).T

    summary_exit = pd.DataFrame({
        p: {
            f"Guaranteed ({exit_rate_label} p.a.)": (0.0 if p == "Antoine" else g_display[p]),
            "Final (exit residual)": results_exit[p],
        } for p in parts
    }).T

    # Compute prices for today and sell date (with interpolation fallback)
    try:
        price_today = float(price_series.sort_index().loc[pd.Timestamp(TODAY)])
    except KeyError:
        price_today = float(
            price_series.sort_index()
            .reindex(price_series.index.union([pd.Timestamp(TODAY)])).interpolate(method="time")
            .loc[pd.Timestamp(TODAY)]
        )
    try:
        price_sell_val = float(price_series.sort_index().loc[pd.Timestamp(sell_date)])
    except KeyError:
        price_sell_val = float(
            price_series.sort_index()
            .reindex(price_series.index.union([pd.Timestamp(sell_date)])).interpolate(method="time")
            .loc[pd.Timestamp(sell_date)]
        )

    # ---- Render top metrics in the placeholder (two rows) ----
    with metrics_box:
        # Row 1: Gains (lightweight cards) — USD primary, AED secondary
        def small_metric(label: str, primary_value: str, secondary_value: str | None = None):
            st.markdown(f"""
            <div style="border:1px solid rgba(49,51,63,0.15); border-radius:12px; padding:12px 16px; background:rgba(250,250,250,0.6);">
              <div style="font-size:0.95rem; color:rgba(49,51,63,0.75); margin-bottom:6px;">{label}</div>
              <div style="font-size:1.6rem; font-weight:800; line-height:1.15; margin-bottom:2px;">{primary_value}</div>
              {f'<div style="font-size:1.0rem; color:rgba(49,51,63,0.7);">{secondary_value}</div>' if secondary_value else ''}
            </div>
            """, unsafe_allow_html=True)

        aed_today_val  = float(summary_today.loc[selected_participant, "Final (max/residual)"])
        aed_sell_val   = float(summary_sell.loc[selected_participant, "Final (max/residual)"])
        aed_exit_val   = float(summary_exit.loc[selected_participant, "Final (exit residual)"])

        usd_today  = aed_today_val / AED_PER_USD
        usd_sell   = aed_sell_val  / AED_PER_USD
        usd_exit   = aed_exit_val  / AED_PER_USD

        r1c1, r1c2, r1c3 = st.columns(3)
        with r1c1:
            small_metric(
                "Gains TODAY (SALE residual)",
                fmt_usd(usd_today),
                fmt_aed(aed_today_val)
            )
        with r1c2:
            small_metric(
                f"Gains at {sell_date.isoformat()} (SALE residual)",
                fmt_usd(usd_sell),
                fmt_aed(aed_sell_val)
            )
        with r1c3:
            small_metric(
                f"Gains at {sell_date.isoformat()} (EXIT {exit_rate_label} residual)",
                fmt_usd(usd_exit),
                fmt_aed(aed_exit_val)
            )

        # Row 2: Prices (standard metrics)
        r2c1, r2c2 = st.columns(2)
        with r2c1:
            st.metric("Estimated price today", fmt_aed(price_today))
        with r2c2:
            st.metric(f"Estimated price at {sell_date.isoformat()}", fmt_aed(price_sell_val))

    # ---- Sanity checks: sums must match total project appreciation in BOTH SALE and EXIT ----
    total_appreciation_sell = max(price_sell_val - ACQ_PRICE, 0.0)

    sale_sum_final = float(summary_sell["Final (max/residual)"].sum())
    sale_diff = sale_sum_final - total_appreciation_sell

    exit_sum_final = float(summary_exit["Final (exit residual)"].sum())
    exit_diff = exit_sum_final - total_appreciation_sell

    tol = max(1e-6, 1e-9 * max(total_appreciation_sell, 1.0))
    st.subheader("Sanity checks")
    if abs(sale_diff) <= tol:
        st.success(f"SALE check passed: sum of final gains = total appreciation ({sale_sum_final:,.0f} AED).")
    else:
        st.error(f"SALE check FAILED: participants sum {sale_sum_final:,.0f} vs total appreciation {total_appreciation_sell:,.0f} (Δ={sale_diff:,.0f}).")

    if abs(exit_diff) <= tol:
        st.success(f"EXIT {exit_rate_label} check passed: sum of final gains = total appreciation ({exit_sum_final:,.0f} AED).")
    else:
        st.error(f"EXIT {exit_rate_label} check FAILED: participants sum {exit_sum_final:,.0f} vs total appreciation {total_appreciation_sell:,.0f} (Δ={exit_diff:,.0f}).")

    st.subheader("3) Gains breakdown")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**Today – SALE (others: max(app, 15%); Antoine: residual)**")
        st.dataframe(summary_today.style.format("{:,.0f}"), use_container_width=True)
    with col2:
        st.markdown(f"**At {sell_date.isoformat()} – SALE (others: max(app, 15%); Antoine: residual)**")
        st.dataframe(summary_sell.style.format("{:,.0f}"), use_container_width=True)
    with col3:
        st.markdown(f"**At {sell_date.isoformat()} – EXIT @ {exit_rate_label} (others: guarantee; Antoine: residual)**")
        st.dataframe(summary_exit.style.format("{:,.0f}"), use_container_width=True)

    st.subheader("4) Notes & next steps")
    st.markdown(
        f"""
- **Other investors** are computed as residual of the **Total Project Inflow** plan _minus_ Antoine and New investor on each window (never negative).
- **Total Project Inflow** follows the fixed Aldar installment plan embedded in the app (read-only).
- **SALE case (default)**:
  - Other investors receive the greater of **appreciation-based** or **15% p.a. guarantee** (time-weighted).
  - **Antoine** receives the **residual of the project appreciation pot**, i.e. `max(price(t)−acq_price, 0) − sum(others' payouts)`. His **guarantee is 0**.
- **EXIT case**:
  - If the scenario date is **on/before 2028-09-30**, other investors receive **15% p.a.** time-weighted guarantees.
  - If the scenario date is **after 2028-09-30**, other investors receive **20% p.a.** time-weighted guarantees.
  - **Antoine** receives the **residual of the project appreciation pot** after those guarantees.
  - Therefore **Antoine + Others = total project appreciation** in EXIT.
- Acquisition date and price are **fixed**: {ACQ_DATE} and {fmt_aed(ACQ_PRICE)}.
- All dates use **Asia/Dubai**.
"""
    )

# -------------------- CLI fallback + tests --------------------

def _tiny_tests():
    print("Running tiny tests…")
    acq_date = ACQ_DATE
    acq_price = 100.0

    # Windows (minimal set for tests)
    contrib = base_contrib_df([acq_date, date(2024, 10, 15)])
    contrib.loc[pd.Timestamp(acq_date), "Antoine"] = 1000.0
    contrib.loc[:, "Total plan"] = default_total_plan_from(contrib)

    # Price series (long) to test both before and after cutoff
    price_long = linear_price_series(acq_date, acq_price, date(2030, 1, 1), 200.0)
    daily_long = build_daily_invested(contrib, acq_date, date(2030, 1, 1))

    # EXIT before cutoff => 15%
    when1 = date(2028, 9, 30)
    res_exit1, rate1 = exit_gains_at_date(when1, acq_date, acq_price, price_long, daily_long)
    total_app1 = max(float(price_long.loc[pd.Timestamp(when1)]) - acq_price, 0.0)
    assert abs(sum(res_exit1.values()) - total_app1) < 1e-6 and abs(rate1 - 0.15) < 1e-9

    # EXIT after cutoff => 20%
    when2 = date(2028, 10, 1)
    res_exit2, rate2 = exit_gains_at_date(when2, acq_date, acq_price, price_long, daily_long)
    total_app2 = max(float(price_long.loc[pd.Timestamp(when2)]) - acq_price, 0.0)
    assert abs(sum(res_exit2.values()) - total_app2) < 1e-6 and abs(rate2 - 0.20) < 1e-9

    print("All tests passed ✔︎")

def run_cli_fallback():
    print("Streamlit not available — running CLI fallback demo.\n")
    print("Tip: in your conda env run:\n  python -m pip install --upgrade pip\n  python -m pip install streamlit\n  # or: conda install -c conda-forge streamlit\n")

    # Minimal demo matching Antoine's real dates
    acq_date = ACQ_DATE
    acq_price = ACQ_PRICE
    contrib_df = base_contrib_df(INVESTMENT_DATES)
    for d, v in DEFAULT_ANTOINE.items():
        contrib_df.loc[pd.Timestamp(d), "Antoine"] = v
    # Fixed plan
    contrib_df["Total plan"] = 0.0
    for d in INVESTMENT_DATES:
        contrib_df.loc[pd.Timestamp(d), "Total plan"] = ALDAR_PLAN[d]

    price_series = linear_price_series(acq_date, acq_price, INVESTMENT_DATES[-1], acq_price)
    daily = build_daily_invested(contrib_df, acq_date, INVESTMENT_DATES[-1])

    res_today = gains_at_date(TODAY, acq_date, acq_price, price_series, daily)
    res_exit_demo, exit_rate_demo = exit_gains_at_date(TODAY, acq_date, acq_price, price_series, daily)
    print("Gains today (CLI):")
    for k, v in res_today.items():
        print(f"  {k:<16} app={v.appreciation:,.2f}  g15={v.guarantee:,.2f}  sale_final={v.final:,.2f}")
    print(f"Exit residuals at rate {exit_rate_demo*100:.0f}% (sum equals appreciation):")
    print(f"  Sum = {sum(res_exit_demo.values()):,.2f}")

# -------------------- Entrypoint --------------------

if __name__ == "__main__":
    if STREAMLIT_AVAILABLE and "streamlit" in sys.argv[0].lower():
        # When launched via `streamlit run app.py`, Streamlit controls execution.
        pass
    elif STREAMLIT_AVAILABLE:
        _tiny_tests()
        print("\nTo launch the web app, run:  streamlit run app.py\n")
    else:
        run_cli_fallback()

# If Streamlit is available and this script is executed by Streamlit, build the UI.
if STREAMLIT_AVAILABLE:
    try:
        run_streamlit_app()
    except Exception as e:
        if hasattr(st, "exception"):
            st.exception(e)
        else:
            raise
