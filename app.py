from __future__ import annotations
import os
from datetime import datetime, date
import streamlit as st
import pandas as pd

st.set_page_config(
    page_title="Oasis Horizon - Investor Portal",
    page_icon="",  # "💼",
    layout="wide",
    initial_sidebar_state="expanded",  # "auto", "expanded"
)


def show_fatal(msg: str, exc: Exception | None = None):
    st.error(msg)
    if exc:
        st.exception(exc)


# --- Domain logic ---
try:
    from engine import (
        AED,
        EUR,
        USD,
        ACQ_DATE,
        ACQ_PRICE,
        TARGET_DATE,
        TARGET_PRICE,
        INVESTMENT_DATES,
        EDITABLE_START,
        ALDAR_PLAN,
        DEFAULT_ANTOINE,
        CURRENCY_RATES,
        linear_price_series,
        base_contrib_df,
        build_daily_invested,
        gains_at_date,
        exit_gains_at_date,
        per_part_guarantee,
        get_daily_gain_per_dollar,
    )
except Exception as e:
    show_fatal(
        "Could not import engine.py. Make sure engine.py is in the same folder as app.py.",
        e,
    )
    st.stop()

# Authentication and investor defaults are now loaded from Streamlit secrets
# See .streamlit/secrets.toml for configuration


# --- CSS ---
def inject_css():
    # Inject JavaScript to force sidebar visibility
    st.markdown(
        """
    <script>
    document.addEventListener('DOMContentLoaded', function() {
        // Force sidebar to be visible with proper width
        const sidebar = document.querySelector('[data-testid="stSidebar"]');
        if (sidebar) {
            sidebar.style.display = 'block';
            sidebar.style.visibility = 'visible';
            sidebar.style.transform = 'translateX(0)';
            sidebar.style.opacity = '1';
            sidebar.style.width = '250px';
            sidebar.style.minWidth = '250px';
            sidebar.style.maxWidth = '250px';
        }
        
        // Show the collapse control
        const collapseControl = document.querySelector('[data-testid="collapsedControl"]');
        if (collapseControl) {
            collapseControl.style.display = 'block';
            collapseControl.style.visibility = 'visible';
        }
        
        // Also try alternative selectors
        const sidebarAlt = document.querySelector('.stSidebar');
        if (sidebarAlt) {
            sidebarAlt.style.display = 'block';
            sidebarAlt.style.visibility = 'visible';
            sidebarAlt.style.transform = 'translateX(0)';
            sidebarAlt.style.width = '250px';
            sidebarAlt.style.minWidth = '250px';
            sidebarAlt.style.maxWidth = '250px';
        }
    });
    </script>
    """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');

/* Base */
.stApp { font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, sans-serif; background:#f5f6f8; }
#MainMenu, footer, header { visibility: hidden; }

/* Login layout */
.login-left { padding: 40px 32px; max-width: 440px; margin-left: 0; margin-right: auto; }
.login-note { font-size: 12px; color: #475569; line-height: 1.45; }

/* Inputs */
.stTextInput input, .stPassword > div > div > input {
  height: 44px; border-radius: 10px; border: 1px solid #e5e7eb;
}

/* Buttons */
.stButton > button {
  background:#0F766E; color:#fff; border:none; border-radius:10px; font-weight:700;
  padding:.7rem 1.2rem; box-shadow:0 1px 2px rgba(0,0,0,.06); transition:background .15s, box-shadow .15s, transform .02s;
}
.stButton > button:hover { background:#0c5f58; color:#fff; box-shadow:0 4px 10px rgba(0,0,0,.08); }
.stButton > button:active { transform:translateY(1px); background:#0b5852; color:#fff; }

/* App bar title */
.brand { font-weight:800; font-size:20px; color:#0f172a; }

/* ---- Sidebar NAV (top) ---- */
.sb-nav-title {
  font-size:12px; font-weight:800; color:#6b7280; letter-spacing:.4px; text-transform:uppercase;
  margin:10px 14px 6px 14px;
}
.sb-wrap { position: relative; margin: 0 10px 12px 14px; }
.sb-rail {
  position:absolute; left:-8px; top:6px; bottom:6px; width:4px; background:#0F766E; border-radius:4px;
}
.sb-nav { background:transparent; padding:0; margin:0; }
.sb-item {
  display:flex; align-items:center; gap:10px;
  padding:10px 12px; border-radius:10px; font-weight:800; color:#1f2937; text-decoration:none;
  border:1px solid transparent; user-select:none;
}
.sb-item:hover { background:#eef2ff; }
.sb-item .ic { width:20px; height:20px; display:inline-flex; align-items:center; justify-content:center; color:#4f46e5; }
.sb-item.active { background:#eef2ff; color:#1e293b; border:1px solid #e5e7eb; }

/* Sidebar contact us footer */
.sidebar-footer {
  position: fixed; bottom: 20px; left: 10px; width: 250px; font-size: 14px; color: #374151;
}
.sidebar-footer a { text-decoration: none; color: #374151; font-weight: 600; }
.sidebar-footer span { font-size: 16px; margin-right: 6px; }

/* Sidebar styling - responsive and collapsible */
[data-testid="stSidebar"] { 
  width: 250px !important;
  min-width: 250px !important;
  max-width: 250px !important;
}

/* Ensure sidebar content has proper width */
[data-testid="stSidebar"] > div {
  width: 250px !important;
  min-width: 250px !important;
}

/* Mobile responsive sidebar */
@media (max-width: 768px) {
  [data-testid="stSidebar"] {
    width: 280px !important;
    min-width: 280px !important;
    max-width: 280px !important;
  }
  
  [data-testid="stSidebar"] > div {
    width: 280px !important;
    min-width: 280px !important;
  }
  
  /* Allow sidebar to be hidden on mobile */
  [data-testid="stSidebar"][aria-expanded="false"] {
    transform: translateX(-100%) !important;
    visibility: hidden !important;
  }
  
  /* Show sidebar when expanded */
  [data-testid="stSidebar"][aria-expanded="true"] {
    transform: translateX(0) !important;
    visibility: visible !important;
  }
}

/* Ensure collapse control is always visible and functional */
[data-testid="collapsedControl"] { 
  display: block !important; 
  visibility: visible !important;
  z-index: 999 !important;
}

/* Cards: white on grey page */
.stat-card {
  background:#ffffff; border:1px solid #e5e7eb; border-radius:14px;
  box-shadow:0 1px 2px rgba(16,24,40,.04); padding:16px 18px;
}
.stat-card .card-head {
  font-size:12px; color:#6b7280; font-weight:800; letter-spacing:.5px; text-transform:uppercase; margin-bottom:8px;
}
.stat-card hr { border:none; border-top:1px solid #f0f2f5; margin:12px -18px 12px; }
.stat-card .card-value { font-size:24px; font-weight:800; color:#111827; margin:2px 0 4px; }
.stat-card .card-sub { font-size:13px; color:#6b7280; font-weight:600; }

/* Larger variant for Performance */
.stat-card.lg .card-value { font-size:32px; }
.stat-card.lg .card-head { font-size:13px; }

/* Scenario selector card */
.scenario-card { background:#fff; border:1px solid #e5e7eb; border-radius:14px; padding:12px 16px; margin-bottom:8px; }
.scenario-title { font-size:14px; font-weight:800; color:#374151; margin-bottom:8px; }

/* Login right image alignment */
.login-hero {
  margin-top: 22px;          /* tweak this value if you want tighter/looser alignment */
}
@media (max-width: 900px) {
  .login-hero { margin-top: 28px; }
}

</style>
""",
        unsafe_allow_html=True,
    )


# --- UI helpers ---
def appbar():
    with st.container():
        c1, csp, c2 = st.columns([2, 6, 4])
        with c1:
            st.markdown(
                '<div class="brand">Oasis Horizon Fund</div>', unsafe_allow_html=True
            )
            st.caption("Investor Portal")
        with c2:
            cols = st.columns([1.2, 1, 1])
            with cols[0]:
                st.selectbox(
                    "Currency",
                    options=[EUR, USD, AED],
                    index=0,
                    key="currency",
                    label_visibility="collapsed",
                    help="Values shown in your selected currency. Base is AED.",
                )
            with cols[1]:
                st.button("Profile", use_container_width=True, disabled=True)
            with cols[2]:
                if st.button("Log out", use_container_width=True):
                    st.session_state.clear()
                    st.rerun()


def sidebar_nav():
    st.sidebar.markdown(
        '<div class="sb-nav-title">INVESTOR PORTAL</div>', unsafe_allow_html=True
    )
    st.sidebar.markdown(
        """
<div class="sb-wrap">
  <div class="sb-rail"></div>
  <div class="sb-nav">
    <div class="sb-item active">
      <span class="ic">🏠</span>
      <span>Home</span>
    </div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def fmt_currency(amount_aed: float) -> str:
    cur = st.session_state.get("currency", EUR)
    val = amount_aed * CURRENCY_RATES[cur]
    symbol = "€" if cur == EUR else "$" if cur == USD else "AED "
    return f"{symbol}{val:,.0f}"


def fmt_aed(amount_aed: float) -> str:
    """Format amount in AED with commas"""
    return f"AED {amount_aed:,.0f}"


def fmt_aed_compact(amount_aed: float) -> str:
    """Format amount in AED in compact form (e.g., 1.2M, 500K)"""
    if amount_aed >= 1_000_000:
        return f"AED {amount_aed/1_000_000:.1f}M"
    elif amount_aed >= 1_000:
        return f"AED {amount_aed/1_000:.0f}K"
    else:
        return f"AED {amount_aed:.0f}"


def fmt_date(d: date) -> str:
    """Format date as 'DD MMM YYYY'"""
    return d.strftime("%d %b %Y")


def can_see_earliest_sell_date(email: str) -> bool:
    """
    Returns True if this user is allowed to see/select the earliest sell/exit date.
    Configure the allowlist in .streamlit/secrets.toml under:
    [features]
    earliest_sell_date_allowed_users = ["someone@company.com"]
    """
    try:
        # allow admins automatically, if you want that behavior
        if st.session_state.get("role") == "Admin":
            return True
        allowed = st.secrets["features"]["earliest_sell_date_allowed_users"]
        return email in allowed
    except KeyError:
        # if not configured, default to False (hide earliest)
        return False


def can_see_gains(email: str) -> bool:
    """
    Returns True if this user can see gains in the performance section.
    Users not in the list will see "No investment yet".
    Configure the allowlist in .streamlit/secrets.toml under:
    [features]
    gains_allowed_users = ["someone@company.com"]
    """
    try:
        # allow admins automatically
        if st.session_state.get("role") == "Admin":
            return True
        allowed = st.secrets["features"]["gains_allowed_users"]
        return email in allowed
    except KeyError:
        # if not configured, default to True (show gains for everyone)
        return True


# --- Login ---
def login_page():
    inject_css()
    left, right = st.columns([5, 8])
    with left:
        st.markdown('<div class="login-left">', unsafe_allow_html=True)
        st.header("Welcome to Oasis Horizon Fund")
        st.write("Please sign in for access.")
        email = st.text_input(
            "Email address", placeholder="you@company.com", key="login_email"
        )
        pw = st.text_input(
            "Password",
            type="password",
            placeholder="Enter your password",
            key="login_pw",
        )
        col_a, col_b = st.columns([1, 1])
        with col_a:
            if st.button("Sign in", use_container_width=True, key="signin"):
                # Load users from secrets
                USERS = get_users_from_secrets()

                if email in USERS and USERS[email] == pw:
                    st.session_state.user = email
                    user_role = get_user_role(email)
                    st.session_state.role = user_role
                    st.session_state.admin_authed = user_role == "admin"
                    st.rerun()
                else:
                    st.error("Invalid email or password")
        with col_b:
            st.button(
                "Request investor access", use_container_width=True, disabled=True
            )
        st.divider()

        # # Show demo investor credentials from secrets
        # with st.expander("Demo Investor Credentials", expanded=False):
        #     try:
        #         users = st.secrets["authentication"]["users"]
        #         defaults = st.secrets["investor_defaults"]

        #         for user in users:
        #             email = user["email"]
        #             password = user["password"]
        #             role = user["role"]

        #             if role == "admin":
        #                 st.markdown("**Admin:**")
        #                 st.code(f"Email: {email}\nPassword: {password}")
        #             else:
        #                 # Get default contribution for this investor
        #                 default_amount = defaults.get(email, {}).get("2025-09-30", 0)
        #                 st.markdown(f"**{email} ({default_amount}k EUR default):**")
        #                 st.code(f"Email: {email}\nPassword: {password}")
        #     except KeyError:
        #         st.info("Demo credentials not configured in secrets")

        st.markdown(
            "<div class='login-note'><b>Confidentiality notice</b>. This portal may contain confidential or privileged information and is intended only for the account holder.</div>",
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        try:
            # spacer to align top of image with "Welcome..." header
            st.markdown(
                '<div style="height: 68px;"></div>', unsafe_allow_html=True
            )  # tweak 20–40px
            st.image("background.png")  # , use_container_width=True)
        except Exception:
            st.markdown(
                """
            <div style="
                background: linear-gradient(135deg, #0F766E 0%, #0c5f58 100%);
                border-radius: 12px;
                padding: 40px 20px;
                text-align: center;
                color: white;
                margin: 20px 0;
            ">
                <h2 style="color: white; margin: 0 0 10px 0;">🏢</h2>
                <h3 style="color: white; margin: 0 0 8px 0;">Oasis Horizon</h3>
                <p style="color: rgba(255,255,255,0.9); margin: 0; font-size: 14px;">
                    Real Estate Investment Platform
                </p>
            </div>
            """,
                unsafe_allow_html=True,
            )


# --- Helper Functions ---
def get_users_from_secrets():
    """Load users from Streamlit secrets"""
    try:
        users = st.secrets["authentication"]["users"]
        return {user["email"]: user["password"] for user in users}
    except KeyError:
        st.error("Authentication secrets not configured")
        return {}


def get_user_role(email):
    """Get user role from secrets"""
    try:
        users = st.secrets["authentication"]["users"]
        for user in users:
            if user["email"] == email:
                return user["role"]
        return "investor"  # default
    except KeyError:
        return "investor"


def get_investor_defaults_from_secrets():
    """Load investor defaults from secrets"""
    try:
        return st.secrets["investor_defaults"]
    except KeyError:
        return {}


def get_fixed_rates_from_secrets():
    """Load fixed rates from secrets"""
    try:
        return st.secrets["fixed_rates"]
    except KeyError:
        return {}


def get_currency_rate_for_date(date_str: str, currency: str) -> float:
    """Get currency rate for a specific date, using fixed rates if available."""
    fixed_rates = get_fixed_rates_from_secrets()

    # Check if we have fixed rates for this date
    if date_str in fixed_rates:
        if currency == EUR:
            return 1.0 / fixed_rates[date_str]["eur_to_aed"]  # Convert to AED->EUR rate
        elif currency == USD:
            return 1.0 / fixed_rates[date_str]["usd_to_aed"]  # Convert to AED->USD rate
        else:  # AED
            return 1.0

    # Fall back to current rates if no fixed rate available
    return CURRENCY_RATES[currency]


def initialize_investor_defaults():
    """Initialize investor-specific default contributions from secrets."""
    current_user = st.session_state.get("user", "")
    secrets_defaults = get_investor_defaults_from_secrets()

    if current_user in secrets_defaults:
        if "new_investor_contributions" not in st.session_state:
            st.session_state.new_investor_contributions = {}

        # Values in secrets are already in AED, no conversion needed
        for date_str, amount_aed in secrets_defaults[current_user].items():
            st.session_state.new_investor_contributions[date_str] = amount_aed


# --- Sections ---
def section_contributions(
    selected_participant: str, contrib_df: pd.DataFrame
) -> pd.DataFrame:
    st.subheader("Your Contributions")
    with st.container(border=True):
        if selected_participant == "New investor":
            st.caption("Edit your desired contribution schedule")
            selected_currency = st.session_state.get("currency", EUR)

            # Initialize investor-specific defaults
            initialize_investor_defaults()

            # Initialize session state for contributions if not exists
            if "new_investor_contributions" not in st.session_state:
                st.session_state.new_investor_contributions = {}

            # Show all contributions in the same row layout
            editable_dates = [d for d in INVESTMENT_DATES if d >= EDITABLE_START]
            cols = st.columns(len(editable_dates))

            for i, d in enumerate(editable_dates):
                with cols[i]:
                    # Get stored AED value from session state, or use current contrib_df value
                    date_key = d.isoformat()
                    if date_key in st.session_state.new_investor_contributions:
                        current_aed_value = st.session_state.new_investor_contributions[
                            date_key
                        ]
                    else:
                        current_aed_value = contrib_df.loc[
                            pd.Timestamp(d), "New investor"
                        ]
                        st.session_state.new_investor_contributions[date_key] = (
                            current_aed_value
                        )

                    # Convert to display currency using fixed rates for past dates
                    rate = get_currency_rate_for_date(date_key, selected_currency)
                    current_display_value = round(current_aed_value * rate)

                    # Check if this is the fixed date (2025-09-30)
                    fixed_date = date(2025, 9, 30)
                    is_fixed = d == fixed_date

                    if is_fixed:
                        # Show as disabled input for fixed date
                        amt = st.number_input(
                            f"{d.isoformat()} (Fixed)",
                            min_value=0.0,
                            step=10_000.0,
                            value=float(current_display_value),
                            format="%.0f",
                            help=f"Amount in {selected_currency} - This contribution is fixed",
                            key=f"contrib_{date_key}_{selected_currency}",
                            disabled=True,
                        )
                        # Keep the original AED value for fixed date
                        amt_aed = current_aed_value
                    else:
                        # Show as editable input for other dates
                        amt = st.number_input(
                            d.isoformat(),
                            min_value=0.0,
                            step=10_000.0,
                            value=float(current_display_value),
                            format="%.0f",
                            help=f"Amount in {selected_currency}",
                            key=f"contrib_{date_key}_{selected_currency}",
                        )
                        # Convert back to AED for storage using the same rate
                        amt_aed = round(amt / rate)

                    contrib_df.loc[pd.Timestamp(d), "New investor"] = amt_aed
                    # Store in session state
                    st.session_state.new_investor_contributions[date_key] = amt_aed
        else:
            st.caption("Admin view with inline editor")
            selected_currency = st.session_state.get("currency", EUR)

            # Initialize session state for admin contributions if not exists
            if "admin_contributions" not in st.session_state:
                st.session_state.admin_contributions = {}

            edit_idx = [
                pd.Timestamp(d) for d in INVESTMENT_DATES if d >= EDITABLE_START
            ]
            editor_df = contrib_df.loc[
                edit_idx, ["Antoine", "New investor", "Total plan"]
            ].copy()

            # Use stored values from session state if available
            for date_idx in edit_idx:
                date_key = date_idx.date().isoformat()
                if date_key in st.session_state.admin_contributions:
                    stored_values = st.session_state.admin_contributions[date_key]
                    editor_df.loc[date_idx, "Antoine"] = stored_values.get(
                        "Antoine", editor_df.loc[date_idx, "Antoine"]
                    )
                    editor_df.loc[date_idx, "New investor"] = stored_values.get(
                        "New investor", editor_df.loc[date_idx, "New investor"]
                    )

            # Convert AED values to display currency for editing using fixed rates
            for date_idx in editor_df.index:
                date_key = date_idx.date().isoformat()
                rate = get_currency_rate_for_date(date_key, selected_currency)
                editor_df.loc[date_idx, "Antoine"] = (
                    editor_df.loc[date_idx, "Antoine"] * rate
                )
                editor_df.loc[date_idx, "New investor"] = (
                    editor_df.loc[date_idx, "New investor"] * rate
                )
                editor_df.loc[date_idx, "Total plan"] = (
                    editor_df.loc[date_idx, "Total plan"] * rate
                )

            editor_df = editor_df.reset_index().rename(columns={"index": "date"})
            editor_df["date"] = editor_df["date"].dt.strftime("%Y-%m-%d")
            edited = st.data_editor(
                editor_df,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "date": st.column_config.TextColumn("date", disabled=True),
                    "Antoine": st.column_config.NumberColumn(
                        f"Antoine ({selected_currency})",
                        format="%.0f",
                        min_value=0.0,
                        step=50_000.0,
                    ),
                    "New investor": st.column_config.NumberColumn(
                        f"New investor ({selected_currency})",
                        format="%.0f",
                        min_value=0.0,
                        step=50_000.0,
                    ),
                    "Total plan": st.column_config.NumberColumn(
                        f"Total plan ({selected_currency})",
                        format="%.0f",
                        disabled=True,
                    ),
                },
                key="contrib_editor_all",
            )
            edited_dates = pd.to_datetime(edited["date"])

            # Convert back to AED for storage using fixed rates
            for i, date_idx in enumerate(edited_dates):
                date_key = date_idx.date().isoformat()
                rate = get_currency_rate_for_date(date_key, selected_currency)

                contrib_df.loc[date_idx, "Antoine"] = round(
                    pd.to_numeric(edited.iloc[i]["Antoine"], errors="coerce") / rate
                )
                contrib_df.loc[date_idx, "New investor"] = round(
                    pd.to_numeric(edited.iloc[i]["New investor"], errors="coerce")
                    / rate
                )

            # Store values in session state
            for i, date_idx in enumerate(edited_dates):
                date_key = date_idx.date().isoformat()
                st.session_state.admin_contributions[date_key] = {
                    "Antoine": contrib_df.loc[date_idx, "Antoine"],
                    "New investor": contrib_df.loc[date_idx, "New investor"],
                }
    return contrib_df


def section_charts(
    daily_invested: pd.DataFrame,
    price_series: pd.Series,
    selected_participant: str,
    is_admin: bool,
):
    try:
        import altair as alt
    except Exception as e:
        show_fatal("Altair import failed. Did you install requirements.txt?", e)
        return

    st.subheader("Charts")

    # First chart: Investment amounts over time
    st.markdown("**Investment Amounts Over Time**")
    with st.container(border=True):
        di = daily_invested.copy()
        cur = st.session_state.get("currency", EUR)
        for col in ["Antoine", "New investor", "Other investors", "Total"]:
            di[col] = di[col] * CURRENCY_RATES[cur]
        df_all = di.reset_index().rename(columns={"index": "date"})

        if is_admin:
            chart = (
                alt.Chart(df_all)
                .transform_fold(
                    ["Antoine", "New investor", "Other investors"],
                    as_=["participant", "value"],
                )
                .mark_line(
                    strokeWidth=3, point=alt.OverlayMarkDef(size=60, filled=True)
                )
                .encode(
                    x=alt.X(
                        "date:T",
                        axis=alt.Axis(format="%b %Y", labelAngle=0, title=None),
                    ),
                    y=alt.Y("value:Q", title=f"Invested Amount ({cur})"),
                    color=alt.Color(
                        "participant:N",
                        legend=alt.Legend(title="Investor"),
                        scale=alt.Scale(scheme="category10"),
                    ),
                    tooltip=[
                        alt.Tooltip("date:T", title="Date", format="%B %Y"),
                        alt.Tooltip("participant:N", title="Investor"),
                        alt.Tooltip("value:Q", title=f"Amount ({cur})", format=",.0f"),
                    ],
                )
                .properties(height=350)
                .configure_axis(
                    grid=True,
                    gridColor="#f0f0f0",
                    domainColor="#e0e0e0",
                    labelColor="#374151",
                    titleColor="#111827",
                )
                .configure_legend(labelColor="#374151", titleColor="#111827")
            )
        else:
            df_one = df_all[["date", selected_participant]].rename(
                columns={selected_participant: "value"}
            )
            chart = (
                alt.Chart(df_one)
                .mark_line(
                    strokeWidth=3,
                    color="#0F766E",
                    point=alt.OverlayMarkDef(size=60, filled=True, color="#0F766E"),
                )
                .encode(
                    x=alt.X(
                        "date:T",
                        axis=alt.Axis(format="%b %Y", labelAngle=0, title=None),
                    ),
                    y=alt.Y("value:Q", title=f"Invested Amount ({cur})"),
                    tooltip=[
                        alt.Tooltip("date:T", title="Date", format="%B %Y"),
                        alt.Tooltip("value:Q", title=f"Amount ({cur})", format=",.0f"),
                    ],
                )
                .properties(height=350)
                .configure_axis(
                    grid=True,
                    gridColor="#f0f0f0",
                    domainColor="#e0e0e0",
                    labelColor="#374151",
                    titleColor="#111827",
                )
            )

        st.altair_chart(chart, use_container_width=True)

    # Second chart: Unit price over time (as bars) - only for admin
    if is_admin:
        st.markdown("**Unit Price Over Time**")
        with st.container(border=True):
            ps = price_series.reset_index()
            ps.columns = ["date", "price"]

            # Create bar chart for price
            price_chart = (
                alt.Chart(ps)
                .mark_bar(color="#0F766E", cornerRadius=4, opacity=0.8)
                .encode(
                    x=alt.X("date:T", axis=alt.Axis(format="%b %Y", labelAngle=0)),
                    y=alt.Y("price:Q", title="Unit Price (AED)"),
                    tooltip=[
                        alt.Tooltip("date:T", title="Date", format="%B %Y"),
                        alt.Tooltip("price:Q", title="Price (AED)", format=",.0f"),
                    ],
                )
                .properties(height=350)
                .configure_axis(
                    grid=True,
                    gridColor="#f0f0f0",
                    domainColor="#e0e0e0",
                    labelColor="#374151",
                    titleColor="#111827",
                )
            )

            st.altair_chart(price_chart, use_container_width=True)


def render_performance(
    perf_box,
    selected_participant: str,
    price_series: pd.Series,
    sell_date,
    daily_invested: pd.DataFrame,
    contrib_df: pd.DataFrame,
):
    with perf_box:
        st.subheader("Your Performance")
        ps = price_series.sort_index()
        if ps.empty:
            show_fatal("Price series is empty.")
            return 0.0, 0.0

        if datetime.now().date() not in ps.index.date:
            ps = (
                ps.reindex(ps.index.union([pd.Timestamp(datetime.now().date())]))
                .interpolate(method="time")
                .ffill()
                .bfill()
            )
        if pd.Timestamp(sell_date) not in ps.index:
            ps = (
                ps.reindex(ps.index.union([pd.Timestamp(sell_date)]))
                .interpolate(method="time")
                .ffill()
                .bfill()
            )

        price_today_val = float(ps.loc[pd.Timestamp(datetime.now().date())])
        price_sell_val = float(ps.loc[pd.Timestamp(sell_date)])

        try:
            results_today = gains_at_date(
                datetime.now().date(),
                ACQ_DATE,
                ACQ_PRICE,
                ps,
                daily_invested,
                contrib_df,
            )
            results_sell = gains_at_date(
                sell_date, ACQ_DATE, ACQ_PRICE, ps, daily_invested, contrib_df
            )
            results_exit, exit_rate = exit_gains_at_date(
                sell_date, ACQ_DATE, ACQ_PRICE, ps, daily_invested, contrib_df
            )
        except Exception as e:
            show_fatal("Error computing gains.", e)
            return price_today_val, price_sell_val

        aed_today = (
            results_today[selected_participant].final
            if hasattr(results_today[selected_participant], "final")
            else results_today[selected_participant]
        )
        aed_today_guarantee = (
            results_today[selected_participant].guarantee
            if hasattr(results_today[selected_participant], "guarantee")
            else 0.0
        )
        aed_sell = (
            results_sell[selected_participant].final
            if hasattr(results_sell[selected_participant], "final")
            else results_sell[selected_participant]
        )
        aed_exit = results_exit[selected_participant]
        rate = int(round(exit_rate * 100))

        # Check if user should see gains
        user_email = st.session_state.get("user", "")
        show_gains = can_see_gains(user_email)

        # Build the base list for date selector
        base_options = [d.strftime("%Y-%m-%d") for d in INVESTMENT_DATES[3:]]

        # Hide the first date unless this user is allowlisted
        if not can_see_earliest_sell_date(user_email) and len(base_options) > 1:
            date_options = base_options[1:]  # drop the earliest item
        else:
            date_options = base_options

        # If the previously selected value is no longer available, reset it
        prev = st.session_state.get("scenario_main")
        if prev and prev not in date_options:
            st.session_state.pop("scenario_main")

        # Build gains cards with exact alignment
        c1, c2 = st.columns([1, 1])

        # Column 1: Gains Today card (with spacer)
        with c1:
            # Spacer to match Exit date selector height (label + selectbox + spacing)
            st.markdown(
                '<div style="height: 60px; margin-bottom: 8px;"></div>',
                unsafe_allow_html=True,
            )

            gains_today_card = (
                f"""
<div class="stat-card lg">
  <div class="card-head">Gains Today</div>
  <hr>
  <div style="margin-bottom: 12px;">
    <div style="font-size: 0.9rem; color: rgba(49,51,63,0.7); margin-bottom: 4px;">Estimated (max)</div>
    <div class="card-value" style="font-size: 1.4rem; margin-bottom: 8px;">{fmt_currency(aed_today)}</div>
  </div>
  <div>
    <div style="font-size: 0.9rem; color: rgba(49,51,63,0.7); margin-bottom: 4px;">Guaranteed (15% p.a.)</div>
    <div class="card-value" style="font-size: 1.2rem; color: rgba(49,51,63,0.8);">{fmt_currency(aed_today_guarantee)}</div>
  </div>
</div>
"""
                if show_gains
                else f"""
<div class="stat-card lg">
  <div class="card-head">Gains Today</div>
  <hr>
  <div class="card-value" style="font-size: 1.4rem; color: rgba(49,51,63,0.6);">No investment yet</div>
</div>
"""
            )

            st.markdown(gains_today_card, unsafe_allow_html=True)

        # Column 2: Exit date selector + Gains at card
        with c2:
            # Exit date selector row
            col_label, col_select, unused_col = st.columns([2, 3, 3])

            with col_label:
                st.markdown(
                    '<div style="padding-top:8px; font-size:14px; font-weight:800; color:#374151;">Exit date</div>',
                    unsafe_allow_html=True,
                )

            with col_select:
                selected_date_str = st.selectbox(
                    "",
                    options=date_options,
                    index=0,
                    label_visibility="collapsed",
                    key="scenario_main",
                )

            # Convert selected date string to date object for display
            display_sell_date = datetime.strptime(selected_date_str, "%Y-%m-%d").date()

            # Gains at card
            st.markdown(
                f"""
<div class="stat-card lg" style="margin-top: 8px; padding: 20px 18px;">
  <div class="card-head">Gains at {display_sell_date.isoformat()}</div>
  <hr>
  <div style="margin-bottom: 16px;">
    <div style="font-size: 0.9rem; color: rgba(49,51,63,0.7); margin-bottom: 6px;">Estimated (sale)</div>
    <div class="card-value" style="font-size: 1.5rem; margin-bottom: 10px;">{fmt_currency(aed_sell)}</div>
  </div>
  <div>
    <div style="font-size: 0.9rem; color: rgba(49,51,63,0.7); margin-bottom: 6px;">Guaranteed (exit @{rate}% p.a.)</div>
    <div class="card-value" style="font-size: 1.3rem; color: rgba(49,51,63,0.8);">{fmt_currency(aed_exit)}</div>
  </div>
</div>
""",
                unsafe_allow_html=True,
            )

    return price_today_val, price_sell_val


def render_overview(
    overview_box,
    sell_date,
    price_today_val,
    price_sell_val,
    daily_invested,
    price_series,
):
    with overview_box:
        st.markdown("")  # Empty line
        st.markdown("")  # Empty line
        st.subheader("Project Overview")
        c1, c2 = st.columns([1, 1])

        # Calculate appreciation amounts
        appreciation_today = price_today_val - ACQ_PRICE
        appreciation_sell = price_sell_val - ACQ_PRICE

        with c1:
            st.markdown(
                f"""
<div class="stat-card">
  <div class="card-head">Estimated Apartment Price today</div>
  <hr>
  <div class="card-value">{fmt_currency(price_today_val)}</div>
  <div class="card-sub">Estimated appreciation: {fmt_currency(appreciation_today)}</div>
</div>
""",
                unsafe_allow_html=True,
            )

            # Calculate and display daily gain per dollar
            try:
                daily_gain_today = get_daily_gain_per_dollar(
                    datetime.now().date(),
                    ACQ_DATE,
                    ACQ_PRICE,
                    price_series,
                    daily_invested,
                )
                # Convert to basis points for better readability (multiply by 10000 to get bp)
                daily_gain_bp = daily_gain_today * 10000

                if daily_gain_today > 0:
                    annual_rate = daily_gain_today * 365 * 100
                    st.markdown(
                        f"""
<div class="stat-card" style="margin-top: 12px;">
  <div class="card-head">Today's Estimated Return for New Investments</div>
  <hr>
  <div class="card-value">{annual_rate:.2f}%</div>
  <div class="card-sub">Annualized rate per dollar invested today</div>
</div>
""",
                        unsafe_allow_html=True,
                    )
            except Exception:
                # Silently fail if there's an error calculating
                pass

        with c2:
            st.markdown(
                f"""
<div class="stat-card">
  <div class="card-head">Estimated Apartment Price at {sell_date.isoformat()}</div>
  <hr>
  <div class="card-value">{fmt_currency(price_sell_val)}</div>
  <div class="card-sub">Estimated appreciation: {fmt_currency(appreciation_sell)}</div>
</div>
""",
                unsafe_allow_html=True,
            )
        # c3 is left empty as requested


# --- Main App ---
def main_app():
    inject_css()
    appbar()
    sidebar_nav()

    is_admin = st.session_state.get("role") == "Admin"

    # Admin can choose whose view to display
    if is_admin:
        selected_participant = st.sidebar.selectbox(
            "View as", ["New investor", "Antoine", "Other investors"], index=0
        )
    else:
        selected_participant = "New investor"

    # ---- Scenario selector (1/3 width) ----
    # Place selector in the first column of a 1:2 split so it occupies ~33% width.
    # Build series
    try:
        price_series = linear_price_series(
            ACQ_DATE, ACQ_PRICE, TARGET_DATE, TARGET_PRICE
        )
    except Exception as e:
        show_fatal("Failed to build price series.", e)
        return

    # Calculate current appreciation for chapeau
    ps_today = price_series.sort_index()
    if datetime.now().date() not in ps_today.index.date:
        ps_today = (
            ps_today.reindex(
                ps_today.index.union([pd.Timestamp(datetime.now().date())])
            )
            .interpolate(method="time")
            .ffill()
            .bfill()
        )
    current_price = float(ps_today.loc[pd.Timestamp(datetime.now().date())])
    appreciation_blurb = current_price - ACQ_PRICE

    # Build target HTML
    target_html = f"<div>Target sale: <strong>{fmt_aed(TARGET_PRICE)}</strong> by <strong>{fmt_date(TARGET_DATE)}</strong></div>"

    # Chapeau - Investment Overview
    st.markdown(
        f"""
<div style="border:1px solid rgba(194,178,128,0.3); border-radius:12px; padding:18px 20px; background:linear-gradient(135deg, #faf8f3 0%, #f5f2eb 100%); line-height:1.65; box-shadow:0 2px 4px rgba(0,0,0,0.02);">
  <div style="margin-bottom:14px; padding-bottom:12px; border-bottom:1px solid rgba(194,178,128,0.2);">
    <strong style="font-size:1.05em; color:#2c2416;">Investment Overview</strong>
  </div>
  <ul style="margin:0; padding-left:20px; list-style-type:disc;">
    <li style="margin-bottom:10px;"><strong>Prime Abu Dhabi property</strong> that has already appreciated by <strong style="color:#0F766E;">{fmt_aed_compact(appreciation_blurb)}</strong> since acquisition</li>
    <li style="margin-bottom:10px;">Capital returned first, investors receive a <strong>15% annualized preferred return</strong>, and profits above that are shared fairly on a <strong>daily pro-rata basis</strong></li>
    <li style="margin-bottom:10px;"><strong>Flexible liquidity:</strong> exit every 8 months at <strong>15% p.a.</strong> (via contractual buy-out), or <strong>automatically at 20% p.a.</strong> if property not sold by <strong>30 Sep 2028</strong></li>
  </ul>
  <div style="margin-top:14px; padding-top:12px; border-top:1px solid rgba(194,178,128,0.2); font-size:0.92em; color:#5a5444;">
    <strong>Purchase:</strong> {fmt_aed(ACQ_PRICE)} on {fmt_date(ACQ_DATE)} &nbsp;•&nbsp; <strong>Target sale:</strong> {fmt_aed(TARGET_PRICE)} by {fmt_date(TARGET_DATE)}
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    st.markdown("")  # Add some spacing

    # col_left, col_mid, col_right = st.columns([1, 1, 3])
    # # with col_left:
    # #     st.markdown(
    # #         '<div class="scenario-card"><div class="scenario-title">Sell / exit date</div>',
    # #         unsafe_allow_html=True,
    # #     )
    # #     date_options = [
    # #         d.strftime("%Y-%m-%d") for d in INVESTMENT_DATES[3:]
    # #     ]  # start at 2026-05-30
    # #     selected_date_str = st.selectbox(
    # #         "",
    # #         options=date_options,
    # #         index=0,
    # #         label_visibility="collapsed",
    # #         key="scenario_main",
    # #     )
    # #     st.markdown("</div>", unsafe_allow_html=True)
    # # empty right column is just spacing to keep 1/3 width
    # with col_left:
    #     st.markdown(
    #         '<div class="scenario-card"><div class="scenario-title">Exit date</div>',
    #         unsafe_allow_html=True,
    #     )

    # with col_mid:
    #     # Build the base list you currently expose (starting at index 3 = 2026-05-30)
    #     base_options = [d.strftime("%Y-%m-%d") for d in INVESTMENT_DATES[3:]]

    #     # Hide the first date unless this user is allowlisted
    #     user_email = st.session_state.get("user", "")
    #     if not can_see_earliest_sell_date(user_email) and len(base_options) > 1:
    #         date_options = base_options[1:]  # drop the earliest item
    #     else:
    #         date_options = base_options

    #     # If the previously selected value is no longer available, reset it
    #     prev = st.session_state.get("scenario_main")
    #     if prev and prev not in date_options:
    #         st.session_state.pop("scenario_main")

    #     selected_date_str = st.selectbox(
    #         "",
    #         options=date_options,
    #         index=0,
    #         label_visibility="collapsed",
    #         key="scenario_main_",
    #     )
    #     st.markdown("</div>", unsafe_allow_html=True)

    # sell_date = datetime.strptime(selected_date_str, "%Y-%m-%d").date()

    # Get sell_date from session state (set by the selector in render_performance)
    # Use a default if not set yet
    if "scenario_main" in st.session_state and st.session_state["scenario_main"]:
        sell_date = datetime.strptime(
            st.session_state["scenario_main"], "%Y-%m-%d"
        ).date()
    else:
        # Default to first available date
        user_email = st.session_state.get("user", "")
        base_options = [d for d in INVESTMENT_DATES[3:]]
        if not can_see_earliest_sell_date(user_email) and len(base_options) > 1:
            sell_date = base_options[1]
        else:
            sell_date = base_options[0]

    # Base contributions
    contrib_df = base_contrib_df(INVESTMENT_DATES)
    for d, v in DEFAULT_ANTOINE.items():
        contrib_df.loc[pd.Timestamp(d), "Antoine"] = v
    for d in INVESTMENT_DATES:
        contrib_df.loc[pd.Timestamp(d), "Total plan"] = ALDAR_PLAN.get(d, 0.0)

    # Create containers for layout order (Performance, Contributions, Overview)
    perf_box = st.container()
    contrib_box = st.container()
    overview_box = st.container()

    # Editor - render into contrib_box
    with contrib_box:
        contrib_df = section_contributions(selected_participant, contrib_df)

    # Invested balances
    end_for_invested = max(sell_date, price_series.index.max().date())
    try:
        daily_invested = build_daily_invested(contrib_df, ACQ_DATE, end_for_invested)
    except Exception as e:
        show_fatal("Failed to build invested balances.", e)
        return

    # Performance & Overview
    price_today_val, price_sell_val = render_performance(
        perf_box,
        selected_participant,
        price_series,
        sell_date,
        daily_invested,
        contrib_df,
    )
    render_overview(
        overview_box,
        sell_date,
        price_today_val,
        price_sell_val,
        daily_invested,
        price_series,
    )

    # Charts
    section_charts(daily_invested, price_series, selected_participant, is_admin)

    # Sidebar footer
    st.sidebar.markdown("---")
    st.sidebar.markdown(
        """
        <div class="sidebar-footer">
            <span>💬</span>
            <a href="mailto:support@oasishorizon.com" target="_blank">Contact us</a>
        </div>
        """,
        unsafe_allow_html=True,
    )


# --- Entrypoint ---
def run():
    try:
        if "admin_authed" not in st.session_state:
            st.session_state.admin_authed = False
        if "user" not in st.session_state:
            login_page()
            return
        main_app()
    except Exception as e:
        show_fatal("Unhandled error. See details below.", e)


if __name__ == "__main__":
    run()
