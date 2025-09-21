# app.py
# Arthouse Co-Investment (Streamlit)
# ---------------------------------------------------------------------------------------
# Public default = "New investor" view.
# Admin-only views ("Antoine" and "Other investors") unlocked via sidebar Admin mode + password.
#
# Admin password:
#   - default: "changeme"
#   - override by setting env var: ARTHOUSE_ADMIN_PW
#
# Core economics (unchanged from your last version):
# - SALE case: Others get max(appreciation-based, 15% p.a. guarantee); Antoine gets residual of project appreciation.
# - EXIT case: If date ≤ 2028-09-30 -> 15% p.a. for Others; if date > 2028-09-30 -> 20% p.a. for Others; Antoine gets residual.
# - New investor gets horizontal editable table; Antoine/Others view shows vertical inline editor.
# - Sanity checks hidden when viewing New investor.

from __future__ import annotations
import os
import sys
from dataclasses import dataclass
from typing import Dict, List, Tuple
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
import pytz

STREAMLIT_AVAILABLE = True
try:
    import streamlit as st
except Exception:
    STREAMLIT_AVAILABLE = False

ALT_AVAILABLE = True
try:
    import altair as alt
except Exception:
    ALT_AVAILABLE = False

# -------------------- Constants & Defaults --------------------
AED = "AED"
EUR = "EUR"
USD = "USD"
ACQ_DATE: date = date(2024, 9, 30)
ACQ_PRICE: float = 11_800_000.0
TARGET_DATE: date = date(2028, 5, 30)
TARGET_PRICE: float = 17_500_000.0
AED_PER_USD: float = 3.6727
AED_PER_EUR: float = 4.31371

# Currency conversion rates (all relative to AED)
CURRENCY_RATES = {
    AED: 1.0,
    USD: 1.0 / AED_PER_USD,
    EUR: 1.0 / AED_PER_EUR,
}

INVESTMENT_DATES: List[date] = [
    date(2024, 9, 30),
    date(2025, 1, 31),
    date(2025, 9, 30),
    date(2026, 5, 30),  # default scenario date (4th)
    date(2027, 1, 30),
    date(2027, 9, 30),
    date(2028, 5, 30),
    date(2028, 9, 30),  # Added for scenario sell options
]

EDITABLE_START: date = date(2025, 9, 30)

ALDAR_PLAN: Dict[date, float] = {
    date(2024, 9, 30): 1_188_000.0,
    date(2025, 1, 31): 1_188_000.0,
    date(2025, 9, 30): 1_188_000.0,
    date(2026, 5, 30): 1_782_000.0,  # special
    date(2027, 1, 30): 1_188_000.0,
    date(2027, 9, 30): 1_188_000.0,
    date(2028, 5, 30): 4_158_000.0,  # special
}

DEFAULT_ANTOINE: Dict[date, float] = {
    date(2024, 9, 30): 1_188_000.0,
    date(2025, 1, 31): 1_188_000.0,
}

DUBAI_TZ = pytz.timezone("Asia/Dubai")
TODAY = datetime.now(DUBAI_TZ).date()

# EXIT rule
EXIT_RATE_CUTOFF = date(2028, 9, 30)  # when > cutoff => 20% p.a., else 15% p.a.

# Admin password
ADMIN_PASSWORD = os.environ.get("ARTHOUSE_ADMIN_PW", "changeme")


# -------------------- Helpers --------------------
def convert_currency(amount_aed: float, target_currency: str) -> float:
    """Convert AED amount to target currency."""
    return amount_aed * CURRENCY_RATES[target_currency]


def fmt_currency(x: float, currency: str) -> str:
    """Format amount in the specified currency."""
    try:
        converted = convert_currency(x, currency)
        if currency == USD:
            return f"${converted:,.0f}"
        elif currency == EUR:
            return f"€{converted:,.0f}"
        else:  # AED
            return f"{converted:,.0f} {AED}"
    except Exception:
        return f"{x} {currency}"


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


def fmt_aed_compact(x: float) -> str:
    if x >= 1_000_000:
        return f"≈ AED {x/1_000_000:.1f}m"
    if x >= 1_000:
        return f"≈ AED {x/1_000:.1f}k"
    return f"≈ AED {x:,.0f}"


def fmt_date(d: date) -> str:
    return pd.Timestamp(d).strftime("%d %b %Y")


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


def linear_price_series(
    acq_date: date, acq_price: float, target_date: date, target_price: float
) -> pd.Series:
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
    s = pd.Series(df["price"].values, index=pd.to_datetime(df["date"])).sort_index()
    s.name = "price"
    return s


def build_daily_invested(
    contrib_df: pd.DataFrame, acq_date: date, end_date: date
) -> pd.DataFrame:
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
    """SALE case: Others get max(app, 15%); Antoine gets residual of project appreciation (no guarantee)."""
    start = acq_date + timedelta(days=1)
    if when <= acq_date:
        zero = GainBreakdown(0.0, 0.0, 0.0)
        return {"Antoine": zero, "New investor": zero, "Other investors": zero}

    idx = make_daily_index(start, when)

    ps = price_series.copy().sort_index()
    if pd.Timestamp(when) not in ps.index:
        full_idx = pd.DatetimeIndex(
            sorted(
                set(ps.index.tolist() + [pd.Timestamp(when), pd.Timestamp(acq_date)])
            )
        )
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
    guarantee_raw = (
        inv[["Antoine", "New investor", "Other investors"]].sum(axis=0) * rate_daily_15
    )

    out: Dict[str, GainBreakdown] = {}
    # Others: max(app, 15%)
    others = ["New investor", "Other investors"]
    others_payout_sum = 0.0
    for col in others:
        app = float(appreciation[col])
        gte = float(guarantee_raw[col])
        final = max(app, gte)
        others_payout_sum += final
        out[col] = GainBreakdown(appreciation=app, guarantee=gte, final=final)

    # Antoine: residual of total appreciation
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
    """Time-weighted guarantee per participant at a single annual rate."""
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
    """EXIT: Others guarantee at 15% p.a. if when ≤ cutoff else 20% p.a.; Antoine = residual of project appreciation."""
    ps = price_series.copy().sort_index()
    if pd.Timestamp(when) not in ps.index:
        full_idx = pd.DatetimeIndex(
            sorted(
                set(ps.index.tolist() + [pd.Timestamp(when), pd.Timestamp(acq_date)])
            )
        )
        ps = ps.reindex(full_idx).interpolate(method="time").ffill().bfill()
    price_t = float(ps.loc[pd.Timestamp(when)])
    total_appreciation = max(price_t - acq_price, 0.0)

    rate_annual = 0.20 if when >= EXIT_RATE_CUTOFF else 0.15
    g = per_part_guarantee(when, acq_date, daily_invested, rate_annual=rate_annual)
    others_sum = g["New investor"] + g["Other investors"]
    ant_residual = total_appreciation - others_sum

    return (
        {
            "Antoine": ant_residual,
            "New investor": g["New investor"],
            "Other investors": g["Other investors"],
        },
        rate_annual,
    )


# -------------------- Login System --------------------
def login_page():
    st.set_page_config(
        page_title="🌴 Arthouse Co-Investment", page_icon="🏗️", layout="wide"
    )

    # Initialize admin login state
    if "show_admin_login" not in st.session_state:
        st.session_state.show_admin_login = False

    # Header with discrete admin button
    col_title, col_admin = st.columns([4, 1])
    with col_title:
        st.title("🌴 Arthouse Co-Investment")
    with col_admin:
        if st.button("⚙️", help="Admin access", key="admin_access_btn"):
            st.session_state.show_admin_login = True

    st.header("Welcome! Please log in to continue")

    st.markdown(
        """
    This application helps you track and analyze your real estate co-investment in the Arthouse project.
    
    """
    )
    st.markdown("**Enter your email address to login or continue as New Investors**")
    # Create columns to left-align the form elements
    col1, col2 = st.columns([1, 3.5])

    with col1:

        email = st.text_input(
            "Email", placeholder="your.email@example.com", key="login_email"
        )

        new_investor_button = st.button(
            "🆕 Continue as New Investor",
            help="Explore the platform without registration",
        )

    # Handle login attempts
    login_attempted = False

    # Check if email was entered and user pressed Enter or clicked elsewhere
    if email and email.strip():
        login_attempted = True
        # For now, all emails show "not registered" message
        st.error(
            "📧 Email not registered - please contact admin or explore as New Investor"
        )

        # Handle New Investor button
    if new_investor_button:
        st.session_state.role = "New Investor"
        st.session_state.admin_authed = False
        st.rerun()

    # Admin login form (appears when admin button is clicked)
    if st.session_state.get("show_admin_login", False):
        st.markdown("---")
        col1, col2 = st.columns([1, 3.5])
        with col1:
            st.markdown("**🔐 Admin Login**")
            admin_password = st.text_input(
                "Password",
                type="password",
                key="admin_login_password",
                placeholder="Enter admin password",
            )

            col_login, col_cancel = st.columns([1, 1])
            with col_login:
                if st.button("Login"):
                    if admin_password == ADMIN_PASSWORD:
                        st.session_state.role = "Admin"
                        st.session_state.admin_authed = True
                        st.session_state.show_admin_login = False
                        st.rerun()
                    else:
                        st.error("Incorrect password")

            with col_cancel:
                if st.button("Cancel"):
                    st.session_state.show_admin_login = False
                    st.rerun()


def logout():
    st.session_state.role = None
    st.session_state.admin_authed = False
    st.rerun()


# -------------------- Main App --------------------
def main_app():
    st.set_page_config(
        page_title="🌴 Arthouse Co-Investment", page_icon="🏗️", layout="wide"
    )

    # ---- Header with title, currency selector, and logout ----
    col1, col2, col3 = st.columns([2.5, 0.5, 1])
    with col1:
        st.title("🌴 Arthouse Co-Investment")
    with col2:
        selected_currency = st.selectbox(
            "Currency",
            [EUR, USD, AED],
            index=0,
            help="All calculations are done in AED and converted for display",
            key="currency_selector",
            label_visibility="collapsed",
        )
        st.session_state.selected_currency = selected_currency
    with col3:

        if st.button("🚪 Log out"):
            logout()

    # ---- Sidebar Configuration ----
    st.sidebar.title("⚙️ Configuration")

    # Determine user permissions
    is_admin = st.session_state.role == "Admin" and st.session_state.get(
        "admin_authed", False
    )

    # Show role info in sidebar
    st.sidebar.markdown("---")
    # st.sidebar.markdown(f"**Current Role:** {st.session_state.role}")
    # if is_admin:
    #     st.sidebar.success("Admin access granted")


# -------------------- Streamlit UI --------------------
def run_streamlit_app():
    # Initialize session state
    if "role" not in st.session_state:
        st.session_state.role = None
    if "admin_authed" not in st.session_state:
        st.session_state.admin_authed = False

    # Show login page or main app
    if st.session_state.role is None:
        login_page()
        return

    # Main app logic
    main_app()

    # Get currency from sidebar (set in main_app)
    selected_currency = st.session_state.get("selected_currency", EUR)
    if "selected_currency" not in st.session_state:
        # Set default if not in session state yet
        selected_currency = EUR
        st.session_state.selected_currency = selected_currency

    # Update selected_currency from sidebar
    try:
        # This will be set by the sidebar selectbox in main_app
        selected_currency = st.session_state.selected_currency
    except:
        selected_currency = EUR

    # Determine user permissions and participant
    is_admin = st.session_state.role == "Admin" and st.session_state.get(
        "admin_authed", False
    )

    if st.session_state.role == "New Investor":
        selected_participant = "New investor"
    else:  # Admin
        # Admin can select participant
        st.sidebar.markdown("---")
        selected_participant = st.sidebar.selectbox(
            "👤 View as",
            ["New investor", "Antoine", "Other investors"],
            index=0,
            help="Select which participant's view to display",
        )

    # ---- Price series ----
    price_series = linear_price_series(ACQ_DATE, ACQ_PRICE, TARGET_DATE, TARGET_PRICE)

    # Scenario date (available in both modes)
    default_scenario_date = INVESTMENT_DATES[3]  # 4th installment

    # Create selectbox with installment dates
    date_options = [d.strftime("%Y-%m-%d") for d in INVESTMENT_DATES]
    default_index = INVESTMENT_DATES.index(default_scenario_date)

    selected_date_str = st.sidebar.selectbox(
        "Scenario: sell / withdraw date",
        options=date_options[3:],
        index=0,  # default_index,
        help="Choose from available installment dates",
    )

    # Convert back to date object
    sell_date = datetime.strptime(selected_date_str, "%Y-%m-%d").date()
    # st.sidebar.caption("Daily indices computed in Asia/Dubai time. Gains today use today's Dubai date.")

    # ---- Blurb inputs ----
    try:
        price_today_blurb = float(price_series.sort_index().loc[pd.Timestamp(TODAY)])
    except KeyError:
        price_today_blurb = float(
            price_series.sort_index()
            .reindex(price_series.index.union([pd.Timestamp(TODAY)]))
            .interpolate(method="time")
            .loc[pd.Timestamp(TODAY)]
        )
    appreciation_blurb = max(price_today_blurb - ACQ_PRICE, 0.0)

    # ---- Title & Intro ----
    # st.title("🌴 Arthouse Co-Investment")
    show_target_line = selected_participant in ("Antoine", "Other investors")
    target_html = (
        f'<div style="margin-top:6px; color:rgba(49,51,63,0.75);">'
        f"Target: <strong>{fmt_currency(TARGET_PRICE, selected_currency)}</strong> on <strong>{fmt_date(TARGET_DATE)}</strong>"
        f"</div>"
        if show_target_line
        else ""
    )
    st.markdown(
        f"""
<div style="border:1px solid rgba(49,51,63,0.15); border-radius:12px; padding:12px 16px; background:rgba(250,250,250,0.6); line-height:1.55;">
  <div><strong>Investors participate in a prime Abu Dhabi property</strong> that has already appreciated by <strong>{fmt_currency(appreciation_blurb, selected_currency)}</strong> since acquisition.</div>
  <br>
  <div>Capital is returned first, investors receive a <strong>15% annualized preferred return</strong>, and profits above that are shared fairly on a <strong>daily pro-rata</strong> basis.</div>
  <br>
  <div>Liquidity is built in: investors may <strong>exit every 8 months with 15% p.a.</strong> (via contractual buy-out), or <strong>automatically at 20% p.a.</strong> if the property is not sold by <strong>30 Sep 2028</strong>.</div>
  <br>
  <div>Purchase: <strong>{fmt_currency(ACQ_PRICE, selected_currency)}</strong> on <strong>{fmt_date(ACQ_DATE)}</strong></div>
  {target_html}
</div>
   
</div>
""",
        unsafe_allow_html=True,
    )
    st.markdown("<br>", unsafe_allow_html=True)  # space before cards

    metrics_box = st.container()

    # -------------------- 1) Investment windows & contributions --------------------
    st.subheader("Investment contributions")

    contrib_df = base_contrib_df(INVESTMENT_DATES).copy()
    for d, v in DEFAULT_ANTOINE.items():
        if d in contrib_df.index.date:
            contrib_df.loc[pd.Timestamp(d), "Antoine"] = v
    contrib_df["Total plan"] = 0.0
    for d in INVESTMENT_DATES:
        contrib_df.loc[pd.Timestamp(d), "Total plan"] = ALDAR_PLAN.get(d, 0.0)

    with st.expander("Edit contributions", expanded=True):
        if selected_participant == "New investor":
            st.markdown(f"**Your investments (in {selected_currency})**")
            # st.caption(
            #     f"Columns are dates; the single row is the editable investment amount in {selected_currency}. Windows before 2025-09-30 are hidden."
            # )
            st.caption(f"Please edit your desired contributions.")

            editable_dates = [d for d in INVESTMENT_DATES if d >= EDITABLE_START]
            date_cols = [d.strftime("%Y-%m-%d") for d in editable_dates]

            # Initialize session state for new investor data if not exists
            if "new_investor_data" not in st.session_state:
                # Default value: 75,000 EUR converted to AED for the first installment
                default_eur_amount = 75000.0
                default_aed_amount = round(default_eur_amount * AED_PER_EUR)

                st.session_state.new_investor_data = {}
                for i, d in enumerate(editable_dates):
                    if i == 0:  # First installment gets the default value
                        st.session_state.new_investor_data[d.strftime("%Y-%m-%d")] = (
                            default_aed_amount
                        )
                    else:  # Other installments start at 0
                        st.session_state.new_investor_data[d.strftime("%Y-%m-%d")] = 0.0

            # Create individual number inputs in columns

            # st.caption(
            #     "💡 Tip: If editing the same field twice, you may need to enter the value twice due to Streamlit's reactive behavior."
            # )

            # Create columns for the inputs
            cols = st.columns(len(date_cols))

            for i, col in enumerate(date_cols):
                with cols[i]:
                    # Get current AED value
                    current_aed_value = st.session_state.new_investor_data[col]
                    # Convert to display currency and round to integer
                    current_display_value = round(
                        current_aed_value * CURRENCY_RATES[selected_currency]
                    )

                    # Create number input
                    new_display_value = st.number_input(
                        label=col,
                        value=float(current_display_value),  # Ensure it's a clean float
                        min_value=0.0,
                        step=10000.0,
                        format="%.0f",
                        key=f"investment_{col}_{selected_currency}",
                        help=f"Amount in {selected_currency}",
                    )

                    # Convert back to AED and store (round to avoid precision issues)
                    new_aed_value = round(
                        new_display_value / CURRENCY_RATES[selected_currency]
                    )
                    st.session_state.new_investor_data[col] = new_aed_value
                    contrib_df.loc[pd.Timestamp(col), "New investor"] = new_aed_value

            # st.markdown("---")
            st.markdown(f"**Aldar installment plan (in {selected_currency})**")

            # Create horizontal table like the editable one, but read-only
            all_dates = [d for d in INVESTMENT_DATES]
            all_date_cols = [d.strftime("%Y-%m-%d") for d in all_dates]
            plan_values = [
                round(ALDAR_PLAN.get(d, 0.0) * CURRENCY_RATES[selected_currency])
                for d in all_dates
            ]
            plan_horiz_df = pd.DataFrame(
                [plan_values],
                index=[f"Installment ({selected_currency})"],
                columns=all_date_cols,
            )

            st.dataframe(
                plan_horiz_df.style.format("{:,.0f}"),
                use_container_width=True,
            )

        else:
            st.markdown("**Antoine & New investor (inline)**")
            st.caption("Rows before 2025-09-30 are fixed. Total plan is locked.")
            edit_idx = [
                pd.Timestamp(d) for d in INVESTMENT_DATES if d >= EDITABLE_START
            ]
            editor_df = contrib_df.loc[
                edit_idx, ["Antoine", "New investor", "Total plan"]
            ].copy()
            editor_df = editor_df.reset_index().rename(columns={"index": "date"})
            editor_df["date"] = editor_df["date"].dt.strftime("%Y-%m-%d")

            edited = st.data_editor(
                editor_df,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "date": st.column_config.TextColumn(
                        "date", help="Installment window", disabled=True
                    ),
                    "Antoine": st.column_config.NumberColumn(
                        "Antoine", format="%.0f", min_value=0.0, step=50_000.0
                    ),
                    "New investor": st.column_config.NumberColumn(
                        "New investor", format="%.0f", min_value=0.0, step=50_000.0
                    ),
                    "Total plan": st.column_config.NumberColumn(
                        "Total plan", format="%.0f", disabled=True
                    ),
                },
                key="contrib_editor_all",
            )
            edited_dates = pd.to_datetime(edited["date"])
            contrib_df.loc[edited_dates, "Antoine"] = (
                pd.to_numeric(edited["Antoine"], errors="coerce")
                .fillna(0.0)
                .round()
                .values
            )
            contrib_df.loc[edited_dates, "New investor"] = (
                pd.to_numeric(edited["New investor"], errors="coerce")
                .fillna(0.0)
                .round()
                .values
            )

    # Warn if over plan
    over_by = (contrib_df["Antoine"] + contrib_df["New investor"]) - contrib_df[
        "Total plan"
    ]
    if (over_by > 0).any():
        bad_dates = [d.date().isoformat() for d in contrib_df.index[over_by > 0]]
        st.warning(
            "On some installment dates, Total Investment exceeds Aldar required payment. Residual set to 0 for: "
            + ", ".join(bad_dates)
        )

    # -------------------- 2) Invested balances (daily) --------------------
    end_for_invested = max(
        sell_date,
        TODAY,
        price_series.index.max().date() if len(price_series) else ACQ_DATE,
    )
    daily_invested = build_daily_invested(contrib_df, ACQ_DATE, end_for_invested)

    st.subheader("Invested balances")

    global ALT_AVAILABLE
    try:
        alt = __import__("altair")
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

    di_start, di_end = pd.Timestamp(daily_invested.index.min()), pd.Timestamp(
        daily_invested.index.max()
    )
    di_ticks = _bimonth_ticks(di_start, di_end)

    # All participants chart (Antoine view only)
    if selected_participant == "Antoine":
        if ALT_AVAILABLE:
            df_all = daily_invested.reset_index().rename(columns={"index": "date"})
            # Convert to selected currency for display
            for col in ["Antoine", "New investor", "Other investors"]:
                df_all[col] = df_all[col] * CURRENCY_RATES[selected_currency]

            chart_all = (
                alt.Chart(df_all)
                .transform_fold(
                    ["Antoine", "New investor", "Other investors"],
                    as_=["participant", "value"],
                )
                .mark_line()
                .encode(
                    x=alt.X(
                        "date:T",
                        axis=alt.Axis(format="%b %Y", labelAngle=0, values=di_ticks),
                    ),
                    y=alt.Y("value:Q", title=f"Invested ({selected_currency})"),
                    color=alt.Color(
                        "participant:N", legend=alt.Legend(title="Participant")
                    ),
                )
                .properties(height=300)
            )
            st.altair_chart(chart_all, use_container_width=True)
        else:
            # Convert data for line chart
            daily_invested_display = daily_invested[
                ["Antoine", "New investor", "Other investors"]
            ].copy()
            daily_invested_display = (
                daily_invested_display * CURRENCY_RATES[selected_currency]
            )
            st.line_chart(daily_invested_display)

        # Unit price projection (Antoine only)
        st.markdown("**Unit price over time (projection)**")
        show_usd = st.checkbox(
            "Show price in USD", value=False, help="Convert from AED at fixed 3.6725"
        )
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
        df_price = df_price.dropna().reset_index(drop=True)
        ps_start, ps_end = pd.Timestamp(df_price["date"].min()), pd.Timestamp(
            df_price["date"].max()
        )
        ps_ticks = _bimonth_ticks(ps_start, ps_end)
        if ALT_AVAILABLE and not df_price.empty:
            line = (
                alt.Chart(df_price)
                .mark_line()
                .encode(
                    x=alt.X(
                        "date:T",
                        axis=alt.Axis(format="%b %Y", labelAngle=0, values=ps_ticks),
                    ),
                    y=alt.Y("price:Q", title=y_title),
                )
                .properties(height=300)
            )
            rule_acq = (
                alt.Chart(pd.DataFrame({"date": [pd.Timestamp(ACQ_DATE)]}))
                .mark_rule(strokeDash=[4, 4])
                .encode(x="date:T")
            )
            rule_tgt = (
                alt.Chart(pd.DataFrame({"date": [pd.Timestamp(TARGET_DATE)]}))
                .mark_rule(strokeDash=[4, 4])
                .encode(x="date:T")
            )
            markers_df = pd.DataFrame(
                {
                    "date": [pd.Timestamp(ACQ_DATE), pd.Timestamp(TARGET_DATE)],
                    "price": [acq_p, tgt_p],
                    "label": ["Acquisition", "Target"],
                }
            )
            pts = (
                alt.Chart(markers_df)
                .mark_point(filled=True, size=80)
                .encode(
                    x="date:T",
                    y="price:Q",
                    shape="label:N",
                    tooltip=["label", "date:T", "price:Q"],
                )
            )
            txt = (
                alt.Chart(markers_df)
                .mark_text(align="left", dx=5, dy=-5)
                .encode(x="date:T", y="price:Q", text="label")
            )
            st.altair_chart(
                line + rule_acq + rule_tgt + pts + txt, use_container_width=True
            )
        else:
            st.line_chart(df_price.set_index("date")["price"].to_frame(name=y_title))

    # Selected participant – invested amount
    if ALT_AVAILABLE:
        df_sel = daily_invested.reset_index().rename(columns={"index": "date"})
        # Convert to selected currency for display
        df_sel[selected_participant] = (
            df_sel[selected_participant] * CURRENCY_RATES[selected_currency]
        )

        st.altair_chart(
            alt.Chart(df_sel)
            .mark_line()
            .encode(
                x=alt.X(
                    "date:T",
                    axis=alt.Axis(format="%b %Y", labelAngle=0, values=di_ticks),
                ),
                y=alt.Y(
                    f"{selected_participant}:Q", title=f"Invested ({selected_currency})"
                ),
            )
            .properties(height=300),
            use_container_width=True,
        )
    else:
        # Convert data for line chart
        daily_invested_display = daily_invested[[selected_participant]].copy()
        daily_invested_display = (
            daily_invested_display * CURRENCY_RATES[selected_currency]
        )
        st.line_chart(daily_invested_display)

    # Share of total (scaled ticks)
    share_series = (
        (daily_invested[selected_participant] / daily_invested["Total"])
        .replace([np.inf, -np.inf], np.nan)
        .fillna(0.0)
    )
    share_max = float(share_series.max())
    quintiles = [0.2, 0.4, 0.6, 0.8, 1.0]
    y_max = next((q for q in quintiles if share_max <= q), 1.0)
    y_max = max(0.2, min(1.0, y_max))
    if ALT_AVAILABLE:
        share_df = share_series.reset_index()
        share_df.columns = ["date", "share"]
        tick_vals = [i / 10 for i in range(0, int(y_max * 10) + 1)]
        if share_max < 0.10 and 0.05 not in tick_vals:
            tick_vals = [0.0, 0.05] + [t for t in tick_vals if t != 0.0]
        st.altair_chart(
            alt.Chart(share_df)
            .mark_line()
            .encode(
                x=alt.X(
                    "date:T",
                    axis=alt.Axis(format="%b %Y", labelAngle=0, values=di_ticks),
                ),
                y=alt.Y(
                    "share:Q",
                    title="Share of total amount invested",
                    scale=alt.Scale(domain=[0, y_max]),
                    axis=alt.Axis(format="%", values=tick_vals),
                ),
            )
            .properties(height=300),
            use_container_width=True,
        )
    else:
        st.line_chart(share_series)

    # Ensure price covers sell_date/today
    min_needed_end = max(TODAY, sell_date)
    if price_series.index.max().date() < min_needed_end:
        last_date = price_series.index.max().date()
        last_price = float(price_series.iloc[-1])
        ext_idx = make_daily_index(last_date, min_needed_end)
        add = pd.Series(last_price, index=ext_idx)
        price_series = pd.concat([price_series, add[1:]])

    # -------------------- Gains --------------------
    results_today = gains_at_date(
        TODAY, ACQ_DATE, ACQ_PRICE, price_series, daily_invested
    )
    results_sell = gains_at_date(
        sell_date, ACQ_DATE, ACQ_PRICE, price_series, daily_invested
    )
    results_exit, exit_rate = exit_gains_at_date(
        sell_date, ACQ_DATE, ACQ_PRICE, price_series, daily_invested
    )

    g_display = per_part_guarantee(sell_date, ACQ_DATE, daily_invested, exit_rate)
    exit_rate_label = f"{int(round(exit_rate*100))}%"

    parts = ["Antoine", "New investor", "Other investors"]
    summary_today = pd.DataFrame(
        {
            p: {
                "Appreciation-based": results_today[p].appreciation,
                "Guaranteed (15% p.a.)": (
                    0.0 if p == "Antoine" else results_today[p].guarantee
                ),
                "Final (max/residual)": results_today[p].final,
            }
            for p in parts
        }
    ).T

    summary_sell = pd.DataFrame(
        {
            p: {
                "Appreciation-based": results_sell[p].appreciation,
                "Guaranteed (15% p.a.)": (
                    0.0 if p == "Antoine" else results_sell[p].guarantee
                ),
                "Final (max/residual)": results_sell[p].final,
            }
            for p in parts
        }
    ).T

    summary_exit = pd.DataFrame(
        {
            p: {
                f"Guaranteed ({exit_rate_label} p.a.)": (
                    0.0 if p == "Antoine" else g_display[p]
                ),
                "Final (exit residual)": results_exit[p],
            }
            for p in parts
        }
    ).T

    # Convert all summary dataframes to selected currency
    summary_today_display = summary_today * CURRENCY_RATES[selected_currency]
    summary_sell_display = summary_sell * CURRENCY_RATES[selected_currency]
    summary_exit_display = summary_exit * CURRENCY_RATES[selected_currency]

    # Prices & total appreciation
    try:
        price_today_val = float(price_series.sort_index().loc[pd.Timestamp(TODAY)])
    except KeyError:
        price_today_val = float(
            price_series.sort_index()
            .reindex(price_series.index.union([pd.Timestamp(TODAY)]))
            .interpolate(method="time")
            .loc[pd.Timestamp(TODAY)]
        )
    try:
        price_sell_val = float(price_series.sort_index().loc[pd.Timestamp(sell_date)])
    except KeyError:
        price_sell_val = float(
            price_series.sort_index()
            .reindex(price_series.index.union([pd.Timestamp(sell_date)]))
            .interpolate(method="time")
            .loc[pd.Timestamp(sell_date)]
        )

    total_appreciation_today = max(price_today_val - ACQ_PRICE, 0.0)
    total_appreciation_sell = max(price_sell_val - ACQ_PRICE, 0.0)

    # -------------------- Cards --------------------
    with metrics_box:

        def small_metric(
            label: str, primary_value: str, secondary_value: str | None = None
        ):
            st.markdown(
                f"""
            <div style="border:1px solid rgba(49,51,63,0.15); border-radius:12px; padding:12px 16px; background:rgba(250,250,250,0.6);">
              <div style="font-size:0.95rem; color:rgba(49,51,63,0.75); margin-bottom:6px;">{label}</div>
              <div style="font-size:1.6rem; font-weight:800; line-height:1.15; margin-bottom:2px;">{primary_value}</div>
              {f'<div style="font-size:1.0rem; color:rgba(49,51,63,0.7);">{secondary_value}</div>' if secondary_value else ''}
            </div>
            """,
                unsafe_allow_html=True,
            )

        aed_today_val = float(
            summary_today.loc[selected_participant, "Final (max/residual)"]
        )
        aed_sell_val = float(
            summary_sell.loc[selected_participant, "Final (max/residual)"]
        )
        aed_exit_val = float(
            summary_exit.loc[selected_participant, "Final (exit residual)"]
        )

        usd_today = aed_today_val / AED_PER_USD
        usd_sell = aed_sell_val / AED_PER_USD
        usd_exit = aed_exit_val / AED_PER_USD

        c1, c2, c3 = st.columns(3)
        with c1:
            small_metric(
                "Gains TODAY (from sale)",
                fmt_currency(aed_today_val, selected_currency),
                fmt_aed(aed_today_val) if selected_currency != AED else None,
            )
        with c2:
            small_metric(
                f"Gains at {sell_date.isoformat()} (from sale)",
                fmt_currency(aed_sell_val, selected_currency),
                fmt_aed(aed_sell_val) if selected_currency != AED else None,
            )
        with c3:
            small_metric(
                f"Gains at {sell_date.isoformat()} (EXIT @ {exit_rate_label}, no sale)",
                fmt_currency(aed_exit_val, selected_currency),
                fmt_aed(aed_exit_val) if selected_currency != AED else None,
            )

        r2c1, r2c2, r2c3 = st.columns(3)
        with r2c1:
            st.metric(
                "Estimated total appreciation today",
                fmt_currency(total_appreciation_today, selected_currency),
            )
            st.markdown(
                f"""
                <div style="line-height:1.2; margin-top:2px;">
                                     <div>Estimated price today ({selected_currency})</div>
                   <div style="font-weight:700; font-size:1.15rem; margin-top:1px;">{fmt_currency(price_today_val, selected_currency)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with r2c2:
            st.metric(
                f"Estimated total appreciation at {sell_date.isoformat()}",
                fmt_currency(total_appreciation_sell, selected_currency),
            )
            st.markdown(
                f"""
                <div style="line-height:1.2; margin-top:2px;">
                                     <div>Estimated price at {sell_date.isoformat()} ({selected_currency})</div>
                   <div style="font-weight:700; font-size:1.15rem; margin-top:1px;">{fmt_currency(price_sell_val, selected_currency)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with r2c3:
            # Empty third column as requested
            pass

    # -------------------- Sanity checks --------------------
    if selected_participant != "New investor":
        sale_sum_final = float(summary_sell["Final (max/residual)"].sum())
        exit_sum_final = float(summary_exit["Final (exit residual)"].sum())
        tol = max(1e-6, 1e-9 * max(total_appreciation_sell, 1.0))

        st.subheader("Sanity checks")
        diff_sale = sale_sum_final - total_appreciation_sell
        if abs(diff_sale) <= tol:
            st.success(
                f"SALE check passed: sum of final gains = total appreciation ({fmt_currency(sale_sum_final, selected_currency)})."
            )
        else:
            st.error(
                f"SALE check FAILED: participants sum {fmt_currency(sale_sum_final, selected_currency)} vs total appreciation {fmt_currency(total_appreciation_sell, selected_currency)} (Δ={fmt_currency(diff_sale, selected_currency)})."
            )

        diff_exit = exit_sum_final - total_appreciation_sell
        if abs(diff_exit) <= tol:
            st.success(
                f"EXIT {exit_rate_label} check passed: sum of final gains = total appreciation ({fmt_currency(exit_sum_final, selected_currency)})."
            )
        else:
            st.error(
                f"EXIT {exit_rate_label} check FAILED: participants sum {fmt_currency(exit_sum_final, selected_currency)} vs total appreciation {fmt_currency(total_appreciation_sell, selected_currency)} (Δ={fmt_currency(diff_exit, selected_currency)})."
            )

    # # -------------------- 3) Gains breakdown --------------------
    # st.subheader("3) Gains breakdown")
    # col1, col2, col3 = st.columns(3)
    # with col1:
    #     st.markdown("**Today – SALE (others: max(app, 15%); Antoine: residual)**")
    #     st.dataframe(
    #         summary_today_display.style.format("{:,.0f}"), use_container_width=True
    #     )
    # with col2:
    #     st.markdown(
    #         f"**At {sell_date.isoformat()} – SALE (others: max(app, 15%); Antoine: residual)**"
    #     )
    #     st.dataframe(
    #         summary_sell_display.style.format("{:,.0f}"), use_container_width=True
    #     )
    # with col3:
    #     st.markdown(
    #         f"**At {sell_date.isoformat()} – EXIT @ {exit_rate_label} (others: guarantee; Antoine: residual)**"
    #     )
    #     st.dataframe(
    #         summary_exit_display.style.format("{:,.0f}"), use_container_width=True
    #     )

    # -------------------- 4) Notes --------------------


#     st.subheader("4) Notes & next steps")
#     st.markdown(
#         f"""
# - **Other investors** are computed as residual of the **Total Project Inflow** plan _minus_ Antoine and New investor on each window (never negative).
# - **Total Project Inflow** follows the fixed Aldar installment plan embedded in the app (read-only).
# - **SALE case (default)**:
#   - Other investors receive the greater of **appreciation-based** or **15% p.a. guarantee** (time-weighted).
#   - **Antoine** receives the **residual of the project appreciation** (no guarantee).
# - **EXIT case**:
#   - If the scenario date is **on/before 2028-09-30**, other investors receive **15% p.a.** time-weighted guarantees.
#   - If the scenario date is **after 2028-09-30**, other investors receive **20% p.a.** time-weighted guarantees.
#   - **Antoine** receives the **residual of the project appreciation** after those guarantees.
# - Acquisition date and price are **fixed**: {ACQ_DATE} and {fmt_currency(ACQ_PRICE, selected_currency)}.
# - All dates use **Asia/Dubai**.
# """
#     )


# -------------------- CLI fallback + tests --------------------
def _tiny_tests():
    print("Running tiny tests…")
    acq_date = ACQ_DATE
    acq_price = 100.0
    contrib = base_contrib_df([acq_date, date(2024, 10, 15)])
    contrib.loc[pd.Timestamp(acq_date), "Antoine"] = 1000.0
    contrib.loc[:, "Total plan"] = default_total_plan_from(contrib)
    price_long = linear_price_series(acq_date, acq_price, date(2030, 1, 1), 200.0)
    daily_long = build_daily_invested(contrib, acq_date, date(2030, 1, 1))
    res_sale = gains_at_date(
        date(2024, 10, 1), acq_date, acq_price, price_long, daily_long
    )
    assert "Antoine" in res_sale and "New investor" in res_sale
    when1 = date(2028, 9, 30)
    res_exit1, rate1 = exit_gains_at_date(
        when1, acq_date, acq_price, price_long, daily_long
    )
    total_app1 = max(float(price_long.loc[pd.Timestamp(when1)]) - acq_price, 0.0)
    assert abs(sum(res_exit1.values()) - total_app1) < 1e-6 and abs(rate1 - 0.20) < 1e-9
    when2 = date(2028, 10, 1)
    res_exit2, rate2 = exit_gains_at_date(
        when2, acq_date, acq_price, price_long, daily_long
    )
    total_app2 = max(float(price_long.loc[pd.Timestamp(when2)]) - acq_price, 0.0)
    assert abs(sum(res_exit2.values()) - total_app2) < 1e-6 and abs(rate2 - 0.20) < 1e-9
    print("All tests passed ✔︎")


def run_cli_fallback():
    print("Streamlit not available — running CLI fallback demo.\n")
    print(
        "Tip: in your conda env run:\n  python -m pip install --upgrade pip\n  python -m pip install streamlit\n  # or: conda install -c conda-forge streamlit\n"
    )
    acq_date = ACQ_DATE
    acq_price = ACQ_PRICE
    contrib_df = base_contrib_df(INVESTMENT_DATES)
    for d, v in DEFAULT_ANTOINE.items():
        contrib_df.loc[pd.Timestamp(d), "Antoine"] = v
    contrib_df["Total plan"] = 0.0
    for d in INVESTMENT_DATES:
        contrib_df.loc[pd.Timestamp(d), "Total plan"] = ALDAR_PLAN[d]
    price_series = linear_price_series(
        acq_date, acq_price, INVESTMENT_DATES[-1], acq_price
    )
    daily = build_daily_invested(contrib_df, acq_date, INVESTMENT_DATES[-1])
    res_today = gains_at_date(TODAY, acq_date, acq_price, price_series, daily)
    res_exit_demo, exit_rate_demo = exit_gains_at_date(
        TODAY, acq_date, acq_price, price_series, daily
    )
    print("Gains today (CLI):")
    for k, v in res_today.items():
        print(
            f"  {k:<16} app={v.appreciation:,.2f}  g15={v.guarantee:,.2f}  sale_final={v.final:,.2f}"
        )
    print(
        f"Exit residuals at rate {exit_rate_demo*100:.0f}% (sum equals appreciation):"
    )
    print(f"  Sum = {sum(res_exit_demo.values()):,.2f}")


# -------------------- Entrypoint --------------------
if __name__ == "__main__":
    if STREAMLIT_AVAILABLE and "streamlit" in sys.argv[0].lower():
        pass
    elif STREAMLIT_AVAILABLE:
        _tiny_tests()
        print("\nTo launch the web app, run:  streamlit run app.py\n")
    else:
        run_cli_fallback()

if STREAMLIT_AVAILABLE:
    try:
        run_streamlit_app()
    except Exception as e:
        if hasattr(st, "exception"):
            st.exception(e)
        else:
            raise
