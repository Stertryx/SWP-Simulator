import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import time

# =========================
# APP CONFIG
# =========================
st.set_page_config(page_title="Portfolio SWP Simulator", layout="wide")

st.markdown("""
<style>
    .section-header {
        font-size: 1.05rem;
        font-weight: 700;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        color: #90caf9;
        margin: 28px 0 6px 0;
        border-bottom: 1px solid #0f3460;
        padding-bottom: 6px;
    }
    .insight-box {
        background: #0d1b2a;
        border-left: 3px solid #00b0f6;
        padding: 10px 16px;
        border-radius: 0 8px 8px 0;
        margin: 8px 0;
        font-size: 0.9rem;
        color: #cfd8dc;
    }
    .stButton > button { font-weight: 700; letter-spacing: 0.05em; }
</style>
""", unsafe_allow_html=True)

st.title("Portfolio Analytics: Fixed SWP Monte Carlo")
st.caption("Comprehensive withdrawal strategy simulator with risk analytics")

# =========================
# SIDEBAR PARAMETERS
# =========================
with st.sidebar:
    st.header("Simulation Control")
    run_btn = st.button("RUN SIMULATION", use_container_width=True, type="primary")

    st.divider()
    st.subheader("Investment & SWP")
    initial_investment = st.number_input(
        "Initial Investment (INR)",
        min_value=0,
        step=100000,
        value=None,
        placeholder="e.g. 1,00,000",
        format="%d"
    )
    monthly_withdrawal = st.number_input(
        "Monthly SWP (INR)",
        min_value=0,
        step=1000,
        value=None,
        placeholder="e.g. 10,000",
        format="%d"
    )

    st.subheader("Market Dynamics")
    years = st.slider("Horizon (Years)", 5, 40, 20)
    simulations = st.slider("Simulations Count", 500, 10000, 2000, step=500)

    st.subheader("Inflation Settings")
    use_inflation = st.checkbox("Inflation-Adjusted SWP", value=False)
    inflation_rate_val = st.slider("Annual Inflation (%)", 0.0, 12.0, 6.0)
    inflation_rate = inflation_rate_val / 100

    st.subheader("DIP %")
    d_l = st.number_input(
        "Large Cap DIP %",
        min_value=0.0,
        value=0.0,
        format="%.2f"
    )
    d_f = st.number_input(
        "Flexi Cap DIP %",
        min_value=0.0,
        value=0.0,
        format="%.2f"
    )
    d_m = st.number_input(
        "Mid Cap DIP %",
        min_value=0.0,
        value=0.0,
        format="%.2f"
    )
    d_s = st.number_input(
        "Small Cap DIP %",
        min_value=0.0,
        value=0.0,
        format="%.2f"
    )

    # Use 0 as fallback if not entered yet
    d_l_val = (d_l or 0) / 100
    d_f_val = (d_f or 0) / 100
    d_m_val = (d_m or 0) / 100
    d_s_val = (d_s or 0) / 100

    st.subheader("Asset Allocation (%)")
    c1, c2 = st.columns(2)
    with c1:
        st.caption("Initial Split")
        a_l_val = st.number_input(
            "Large", min_value=0, max_value=100, value=35, format="%d", key="al"
        )
        a_f_val = st.number_input(
            "Flexi", min_value=0, max_value=100, value=30, format="%d", key="af"
        )
        a_m_val = st.number_input(
            "Mid", min_value=0, max_value=100, value=20, format="%d", key="am"
        )
        a_s_val = st.number_input(
            "Small", min_value=0, max_value=100, value=15, format="%d", key="as"
        )
    with c2:
        st.caption("Withdrawal Split")
        w_l_val = st.number_input(
            "Large ", min_value=0, max_value=100, value=35, format="%d", key="wl"
        )
        w_f_val = st.number_input(
            "Flexi ", min_value=0, max_value=100, value=30, format="%d", key="wf"
        )
        w_m_val = st.number_input(
            "Mid ", min_value=0, max_value=100, value=20, format="%d", key="wm"
        )
        w_s_val = st.number_input(
            "Small ", min_value=0, max_value=100, value=15, format="%d", key="ws"
        )

    st.divider()
    st.subheader("Safe SWP Finder")
    target_survival = st.slider("Target Survival Probability (%)", 70, 99, 90)

# Guard: require all inputs before proceeding
missing_inputs = []
if initial_investment is None:
    missing_inputs.append("Initial Investment")
if monthly_withdrawal is None:
    missing_inputs.append("Monthly SWP")
if any(v is None for v in [a_l_val, a_f_val, a_m_val, a_s_val]):
    missing_inputs.append("Initial Split allocation(s)")
if any(v is None for v in [w_l_val, w_f_val, w_m_val, w_s_val]):
    missing_inputs.append("Withdrawal Split allocation(s)")

if missing_inputs:
    st.info("Adjust the parameters in the sidebar and click RUN SIMULATION to begin.")
    st.markdown(f"**Please fill in:** {', '.join(missing_inputs)}")
    st.markdown("""
    **What this simulator includes:**
    - Wealth Projection with P10, P25, P50, P75, P90 confidence bands
    - Drawdown Risk: peak-to-trough decline at median and stress percentiles
    - Asset Allocation Drift: how the portfolio mix evolves over time
    - Withdrawal Coverage Ratio: years of SWP remaining in the corpus
    - Effective Withdrawal Rate vs Blended Expected Return, year by year
    - Safe SWP Finder: binary search for maximum sustainable monthly withdrawal
    - Yearly table with P10/P90 range, coverage ratio, effective rate, and survival probability
    """)
    st.stop()

# Converting whole numbers to decimals for the engine
alloc = np.array([a_l_val, a_f_val, a_m_val, a_s_val]) / 100
withdraw_alloc = np.array([w_l_val, w_f_val, w_m_val, w_s_val]) / 100

if not np.isclose(np.sum(alloc), 1.0) or not np.isclose(np.sum(withdraw_alloc), 1.0):
    st.error(f"Error: Initial Split ({np.sum(alloc)*100:.0f}%) and Withdrawal Split ({np.sum(withdraw_alloc)*100:.0f}%) must both sum to 100%.")
    st.stop()

# =========================
# ENGINE CONSTANTS
# =========================
months = years * 12
returns = np.array([0.12, 0.13, 0.15, 0.17])
vols = np.array([0.16, 0.18, 0.22, 0.28])
mret, mvol = (1 + returns)**(1/12) - 1, vols / np.sqrt(12)
corr = np.array([
    [1.0, 0.9, 0.8, 0.7],
    [0.9, 1.0, 0.85, 0.75],
    [0.8, 0.85, 1.0, 0.85],
    [0.7, 0.75, 0.85, 1.0]
])
L = np.linalg.cholesky(np.outer(mvol, mvol) * corr)
dip_array = np.array([d_l_val, d_f_val, d_m_val, d_s_val])

ASSET_NAMES = ["Large Cap", "Flexi Cap", "Mid Cap", "Small Cap"]
ASSET_COLORS = ["#00b0f6", "#00e676", "#ffd600", "#ff6d00"]


# =========================
# SIMULATION FUNCTIONS
# =========================
def run_simulation_engine():
    paths = np.zeros((simulations, months))
    my_bar = st.progress(0, text="Simulating scenarios...")
    time_display = st.empty()
    start_time = time.time()

    for s in range(simulations):
        if s % 100 == 0:
            pct = (s + 1) / simulations
            my_bar.progress(pct)
            elapsed = time.time() - start_time
            if s > 0:
                est_rem = (elapsed / s) * (simulations - s)
                time_display.caption(f"Estimated time remaining: {est_rem:.1f} seconds")

        port = initial_investment * alloc.copy()
        for m in range(months):
            r = mret + (L @ np.random.normal(size=4))
            if m < 12:
                r += (dip_array / 12) * (1 - m / 12)
            port *= (1 + r)

            inf = (1 + inflation_rate)**(m // 12) if use_inflation else 1
            w_total = monthly_withdrawal * inf
            req = w_total * withdraw_alloc
            for i in range(4):
                if port[i] >= req[i]:
                    port[i] -= req[i]
                else:
                    shortfall = req[i] - port[i]
                    port[i] = 0
                    for j in range(4):
                        if port[j] > 0:
                            take = min(port[j], shortfall)
                            port[j] -= take
                            shortfall -= take
                        if shortfall <= 0:
                            break

            paths[s, m] = np.sum(port)
            if paths[s, m] <= 0:
                break

    my_bar.empty()
    time_display.empty()
    return paths


def run_simulation_engine_fast(w_override):
    """Lightweight version without progress bar, used for binary search."""
    paths = np.zeros((simulations, months))
    for s in range(simulations):
        port = initial_investment * alloc.copy()
        for m in range(months):
            r = mret + (L @ np.random.normal(size=4))
            if m < 12:
                r += (dip_array / 12) * (1 - m / 12)
            port *= (1 + r)
            inf = (1 + inflation_rate)**(m // 12) if use_inflation else 1
            w_total = w_override * inf
            req = w_total * withdraw_alloc
            for i in range(4):
                if port[i] >= req[i]:
                    port[i] -= req[i]
                else:
                    shortfall = req[i] - port[i]
                    port[i] = 0
                    for j in range(4):
                        if port[j] > 0:
                            take = min(port[j], shortfall)
                            port[j] -= take
                            shortfall -= take
                        if shortfall <= 0:
                            break
            paths[s, m] = np.sum(port)
            if paths[s, m] <= 0:
                break
    return paths


def compute_safe_swp():
    """Binary search for max SWP at target survival probability."""
    lo, hi = 1000, monthly_withdrawal * 3
    for _ in range(12):
        mid = (lo + hi) / 2
        test_paths = run_simulation_engine_fast(mid)
        surv = np.mean(test_paths[:, -1] > 0) * 100
        if surv >= target_survival:
            lo = mid
        else:
            hi = mid
    return lo


def run_asset_tracking():
    """Single representative simulation tracking per-asset values (seeded)."""
    np.random.seed(42)
    port = initial_investment * alloc.copy()
    asset_history = np.zeros((months, 4))
    for m in range(months):
        r = mret + (L @ np.random.normal(size=4))
        if m < 12:
            r += (dip_array / 12) * (1 - m / 12)
        port *= (1 + r)
        inf = (1 + inflation_rate)**(m // 12) if use_inflation else 1
        w_total = monthly_withdrawal * inf
        req = w_total * withdraw_alloc
        for i in range(4):
            if port[i] >= req[i]:
                port[i] -= req[i]
            else:
                shortfall = req[i] - port[i]
                port[i] = 0
                for j in range(4):
                    if port[j] > 0:
                        take = min(port[j], shortfall)
                        port[j] -= take
                        shortfall -= take
                    if shortfall <= 0:
                        break
        asset_history[m] = port.copy()
        if np.sum(port) <= 0:
            break
    return asset_history


# =========================
# RESULTS DISPLAY
# =========================
if run_btn:
    paths = run_simulation_engine()
    finals = paths[:, -1]
    p5, p10, p25, p50, p75, p90, p95 = np.percentile(paths, [5, 10, 25, 50, 75, 90, 95], axis=0)
    survival_prob = np.mean(finals > 0) * 100
    survived_finals = finals[finals > 0]
    final_median = np.median(survived_finals) if len(survived_finals) > 0 else 0
    ruined_count = int(np.sum(finals <= 0))

    # ---- BREAK-EVEN MONTH ----
    surviving_pct = np.mean(paths > 0, axis=0)
    breakeven_month = None
    for m in range(months):
        if surviving_pct[m] < 0.5:
            breakeven_month = m + 1
            break

    # ---- DRAWDOWN ----
    running_max = np.maximum.accumulate(paths, axis=1)
    drawdown = (running_max - paths) / np.maximum(running_max, 1)
    p50_drawdown = np.percentile(drawdown, 50, axis=0) * 100
    p90_drawdown = np.percentile(drawdown, 90, axis=0) * 100

    # ---- WITHDRAWAL COVERAGE RATIO ----
    annual_swp = monthly_withdrawal * 12
    wcr_median = p50 / annual_swp
    wcr_p10 = p10 / annual_swp
    wcr_p90 = p90 / annual_swp

    # ---- BLENDED RETURN / SWP RATE ----
    annual_ret_blended = float(np.dot(alloc, returns))
    swp_rate = (monthly_withdrawal * 12) / initial_investment * 100

    # ---- MEDIAN CORPUS CAGR ----
    median_cagr = ((p50[-1] / initial_investment) ** (1 / years) - 1) * 100 if p50[-1] > 0 else 0

    # ---- UPSIDE / DOWNSIDE RATIO ----
    p90_final = p90[-1]
    p10_final = p10[-1]
    upside_downside = (p90_final / p10_final) if p10_final > 0 else float('inf')

    # ---- AVERAGE RUIN MONTH (failed sims only) ----
    ruin_months = []
    for s in range(simulations):
        for m in range(months):
            if paths[s, m] <= 0:
                ruin_months.append(m + 1)
                break
    avg_ruin_month = int(np.mean(ruin_months)) if ruin_months else None

    # ---- SWP SUSTAINABILITY INDEX ----
    sustainability_index = (annual_ret_blended * 100) / swp_rate if swp_rate > 0 else float('inf')

    # ---- TOTAL WITHDRAWN ----
    total_withdrawn = sum(
        monthly_withdrawal * ((1 + inflation_rate)**(m // 12) if use_inflation else 1)
        for m in range(months)
    )

    # ---- ASSET TRACKING ----
    asset_history = run_asset_tracking()
    asset_totals = asset_history.sum(axis=1)
    asset_pct = np.where(asset_totals[:, None] > 0, asset_history / asset_totals[:, None] * 100, 0)

    x_axis = list(range(1, months + 1))
    yr_axis = list(range(1, years + 1))

    # ============================
    # SECTION 1: CORE RESULTS
    # ============================
    st.divider()
    st.markdown('<div class="section-header">Core Results</div>', unsafe_allow_html=True)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Survival Probability", f"{survival_prob:.1f}%",
                help="% of simulations where corpus outlasted the full horizon")
    col2.metric("Median Final Corpus", f"Rs {p50[-1]/1e7:.2f} Cr",
                help="50th percentile ending corpus across all simulations")
    col3.metric("90th Percentile Corpus", f"Rs {p90[-1]/1e7:.2f} Cr",
                help="Optimistic outcome — top 10% of scenarios")
    col4.metric("10th Percentile Corpus", f"Rs {p10[-1]/1e7:.2f} Cr",
                help="Stress outcome — bottom 10% of scenarios")

    col5, col6, col7, col8 = st.columns(4)
    col5.metric("Final Monthly SWP",
                f"Rs {int(monthly_withdrawal * ((1+inflation_rate)**(years-1) if use_inflation else 1)):,}")
    col6.metric("Total Withdrawn Over Horizon", f"Rs {total_withdrawn/1e7:.2f} Cr")
    col7.metric("Portfolio Multiple",
                f"{final_median / initial_investment:.2f}x" if final_median > 0 else "0x",
                help="Median surviving corpus divided by initial investment")
    col8.metric("50% Survival Crossover",
                f"Month {breakeven_month}" if breakeven_month else f"Beyond {years} yrs",
                help="First month when fewer than half the simulations still have corpus remaining")

    # ============================
    # SECTION 2: RISK ANALYTICS
    # ============================
    st.markdown('<div class="section-header">Risk Analytics</div>', unsafe_allow_html=True)

    rc1, rc2, rc3, rc4 = st.columns(4)

    rc1.metric(
        "Median Corpus CAGR",
        f"{median_cagr:.1f}% p.a.",
        help=(
            "Compound annual growth rate of the median corpus from start to end, net of all withdrawals. "
            "A positive CAGR means the portfolio grew in real terms despite monthly withdrawals."
        )
    )
    rc2.metric(
        "SWP Sustainability Index",
        f"{sustainability_index:.2f}x",
        help=(
            "Blended expected annual return divided by the initial SWP rate. "
            "Above 1.0 means returns can fund withdrawals without touching principal. "
            "Below 1.0 means the corpus is being gradually depleted each year."
        )
    )
    rc3.metric(
        "Upside / Downside Ratio",
        f"{upside_downside:.1f}x" if upside_downside != float('inf') else "N/A",
        help=(
            "P90 final corpus divided by P10 final corpus. "
            "A higher value means the gap between good and bad market scenarios is large, "
            "implying significant outcome uncertainty over this horizon."
        )
    )
    rc4.metric(
        "Avg Month of Ruin (Failed Sims)",
        f"Month {avg_ruin_month}" if avg_ruin_month else "No failures",
        help=(
            f"Among the {ruined_count} simulation(s) that depleted the corpus before the horizon ended, "
            "this is the average month when the portfolio hit zero. "
            "An earlier number signals higher sequence-of-returns risk."
        )
    )

    # Insight box
    if swp_rate > annual_ret_blended * 100:
        insight = (
            f"Your SWP rate ({swp_rate:.1f}% p.a.) exceeds the blended expected portfolio return "
            f"({annual_ret_blended*100:.1f}% p.a.). This means the corpus will erode over time in most scenarios. "
            f"Consider reducing the monthly withdrawal, extending the horizon, or shifting allocation toward higher-return assets."
        )
    else:
        headroom = annual_ret_blended * 100 - swp_rate
        insight = (
            f"Your SWP rate ({swp_rate:.1f}% p.a.) is below the blended expected portfolio return "
            f"({annual_ret_blended*100:.1f}% p.a.), leaving {headroom:.1f}% of annual return as a reinvestment buffer. "
            f"The portfolio has room to grow while sustaining withdrawals in most scenarios."
        )
    st.markdown(f'<div class="insight-box">{insight}</div>', unsafe_allow_html=True)

    # ============================
    # CHART 1: WEALTH PROJECTION
    # ============================
    st.markdown('<div class="section-header">Wealth Projection Over Time</div>', unsafe_allow_html=True)

    fig1 = go.Figure()
    fig1.add_trace(go.Scatter(x=x_axis, y=p95/1e7, line=dict(color='rgba(0,176,246,0)'),
                              showlegend=False, hoverinfo='skip'))
    fig1.add_trace(go.Scatter(x=x_axis, y=p5/1e7, fill='tonexty',
                              fillcolor='rgba(0,176,246,0.05)',
                              line=dict(color='rgba(0,176,246,0)'),
                              name="90% Confidence Band", hoverinfo='skip'))
    fig1.add_trace(go.Scatter(x=x_axis, y=p90/1e7, line=dict(color='rgba(0,176,246,0)'),
                              showlegend=False, hoverinfo='skip'))
    fig1.add_trace(go.Scatter(x=x_axis, y=p10/1e7, fill='tonexty',
                              fillcolor='rgba(0,176,246,0.13)',
                              line=dict(color='rgba(0,176,246,0)'),
                              name="80% Confidence Band", hoverinfo='skip'))
    fig1.add_trace(go.Scatter(x=x_axis, y=p75/1e7, line=dict(color='rgba(255,214,0,0)'),
                              showlegend=False, hoverinfo='skip'))
    fig1.add_trace(go.Scatter(x=x_axis, y=p25/1e7, fill='tonexty',
                              fillcolor='rgba(255,214,0,0.09)',
                              line=dict(color='rgba(255,214,0,0)'),
                              name="50% Confidence Band", hoverinfo='skip'))
    fig1.add_trace(go.Scatter(x=x_axis, y=p50/1e7, line=dict(color='#00b0f6', width=3),
                              name="Median Projection"))
    fig1.add_trace(go.Scatter(x=x_axis, y=p90/1e7,
                              line=dict(color='#00e676', width=1.5, dash='dot'),
                              name="P90 (Optimistic)"))
    fig1.add_trace(go.Scatter(x=x_axis, y=p10/1e7,
                              line=dict(color='#ff5252', width=1.5, dash='dot'),
                              name="P10 (Stress)"))
    fig1.add_hline(y=0, line_color="red", line_dash="dash", line_width=1,
                   annotation_text="Ruin Level")
    fig1.update_layout(
        hovermode="x unified", template="plotly_dark", height=480,
        xaxis_title="Month", yaxis_title="Crores (INR)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig1, use_container_width=True)

    # ============================
    # CHART 2: DRAWDOWN RISK
    # ============================
    st.markdown('<div class="section-header">Drawdown Risk Over Time</div>', unsafe_allow_html=True)
    st.caption("Peak-to-trough decline from the portfolio's all-time high at each point in time. The P90 line represents the worst 10% of scenarios.")

    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=x_axis, y=p90_drawdown, fill='tozeroy',
                              fillcolor='rgba(255,82,82,0.15)',
                              line=dict(color='#ff5252', width=2),
                              name="P90 Drawdown (Stress)"))
    fig2.add_trace(go.Scatter(x=x_axis, y=p50_drawdown, fill='tozeroy',
                              fillcolor='rgba(255,214,0,0.1)',
                              line=dict(color='#ffd600', width=2),
                              name="Median Drawdown"))
    fig2.update_layout(
        template="plotly_dark", height=360,
        xaxis_title="Month", yaxis_title="Drawdown from Peak (%)",
        legend=dict(orientation="h", y=1.05)
    )
    st.plotly_chart(fig2, use_container_width=True)

    # ============================
    # CHART 3: ASSET ALLOCATION DRIFT
    # ============================
    st.markdown('<div class="section-header">Asset Allocation Drift (Representative Scenario)</div>', unsafe_allow_html=True)
    st.caption("How the portfolio's asset mix evolves in a single seeded simulation. Assets with heavier withdrawal allocations deplete faster, shifting the overall mix over time.")

    fig3 = go.Figure()
    for i, (name, color) in enumerate(zip(ASSET_NAMES, ASSET_COLORS)):
        fig3.add_trace(go.Scatter(
            x=x_axis, y=asset_pct[:, i], stackgroup='one',
            name=name, line=dict(color=color)
        ))
    fig3.update_layout(
        template="plotly_dark", height=360,
        xaxis_title="Month", yaxis_title="% of Portfolio",
        legend=dict(orientation="h", y=1.05)
    )
    st.plotly_chart(fig3, use_container_width=True)

    # ============================
    # CHART 4: WITHDRAWAL COVERAGE RATIO
    # ============================
    st.markdown('<div class="section-header">Withdrawal Coverage Ratio (Median)</div>', unsafe_allow_html=True)
    st.caption("Median corpus divided by annual SWP — how many more years of withdrawals the portfolio could fund at the current SWP level. Below 10x signals the approaching risk zone.")

    fig4 = go.Figure()
    fig4.add_trace(go.Scatter(x=x_axis, y=wcr_p90,
                              line=dict(color='rgba(0,176,246,0)'),
                              showlegend=False, hoverinfo='skip'))
    fig4.add_trace(go.Scatter(x=x_axis, y=wcr_p10, fill='tonexty',
                              fillcolor='rgba(0,176,246,0.1)',
                              line=dict(color='rgba(0,176,246,0)'),
                              name="P10 to P90 Range", hoverinfo='skip'))
    fig4.add_trace(go.Scatter(x=x_axis, y=wcr_median,
                              line=dict(color='#00e676', width=2.5),
                              name="Median Coverage Ratio"))
    fig4.add_hline(y=10, line_color="#ffd600", line_dash="dash",
                   annotation_text="10x (Caution Zone)")
    fig4.add_hline(y=1, line_color="#ff5252", line_dash="dash",
                   annotation_text="1x (Critical)")
    fig4.update_layout(
        template="plotly_dark", height=360,
        xaxis_title="Month", yaxis_title="Years of SWP Remaining",
        legend=dict(orientation="h", y=1.05)
    )
    st.plotly_chart(fig4, use_container_width=True)

    # ============================
    # CHART 5: EFFECTIVE WITHDRAWAL RATE vs BLENDED RETURN
    # ============================
    st.markdown('<div class="section-header">Effective Withdrawal Rate vs Blended Expected Return</div>', unsafe_allow_html=True)
    st.caption("Effective withdrawal rate each year = annual SWP / median corpus that year. Bars above the dashed line mean withdrawals are drawing down principal.")

    blended_return_pct = annual_ret_blended * 100
    eff_withdrawal_rates = []
    for yr in range(1, years + 1):
        m_idx = (yr * 12) - 1
        med_corpus = np.median(paths[:, m_idx])
        inf = (1 + inflation_rate)**(yr - 1) if use_inflation else 1
        curr_swp_annual = monthly_withdrawal * inf * 12
        eff_rate = (curr_swp_annual / med_corpus * 100) if med_corpus > 0 else 100
        eff_withdrawal_rates.append(eff_rate)

    bar_colors = ['#ff5252' if r > blended_return_pct else '#00b0f6' for r in eff_withdrawal_rates]

    fig5 = go.Figure()
    fig5.add_trace(go.Bar(
        x=yr_axis, y=eff_withdrawal_rates,
        name="Effective Withdrawal Rate (%)",
        marker_color=bar_colors
    ))
    fig5.add_hline(
        y=blended_return_pct, line_color="#ffd600", line_dash="dash",
        annotation_text=f"Blended Expected Return: {blended_return_pct:.1f}%"
    )
    fig5.update_layout(
        template="plotly_dark", height=360,
        xaxis_title="Year", yaxis_title="Rate (%)"
    )
    st.plotly_chart(fig5, use_container_width=True)

    # ============================
    # SAFE SWP FINDER
    # ============================
    st.markdown('<div class="section-header">Safe Withdrawal Rate Finder</div>', unsafe_allow_html=True)

    with st.expander(f"Find Maximum SWP for {target_survival}% Survival Probability (click to run)"):
        st.info("Runs a binary search across withdrawal levels. Takes approximately 30 to 60 seconds depending on simulation count.")
        safe_swp = compute_safe_swp()
        st.success(
            f"For {target_survival}% survival probability over {years} years, "
            f"the safe monthly SWP is approximately Rs {int(safe_swp):,}"
        )
        if safe_swp < monthly_withdrawal:
            delta = monthly_withdrawal - safe_swp
            st.warning(
                f"Your current SWP of Rs {monthly_withdrawal:,} exceeds the safe level by "
                f"Rs {int(delta):,}/month ({delta/safe_swp*100:.1f}%). "
                f"Consider reducing the withdrawal or accepting a lower survival target."
            )
        else:
            delta = safe_swp - monthly_withdrawal
            st.success(
                f"Your current SWP is conservative. Based on this target, you could withdraw "
                f"up to Rs {int(delta):,} more per month while maintaining {target_survival}% survival probability."
            )

    # ============================
    # YEARLY PERFORMANCE TABLE
    # ============================
    st.markdown('<div class="section-header">Yearly Performance Summary (Median)</div>', unsafe_allow_html=True)

    table_data = []
    for yr in range(1, years + 1):
        m_idx = (yr * 12) - 1
        surv = np.mean(paths[:, m_idx] > 0) * 100
        med_val = np.median(paths[:, m_idx])
        p10_val = np.percentile(paths[:, m_idx], 10)
        p90_val = np.percentile(paths[:, m_idx], 90)
        curr_swp = monthly_withdrawal * ((1 + inflation_rate)**(yr - 1) if use_inflation else 1)
        eff_rate = (curr_swp * 12 / med_val * 100) if med_val > 0 else float('inf')
        coverage = (med_val / (curr_swp * 12)) if curr_swp > 0 else 0

        table_data.append({
            "Year": yr,
            "Median Corpus": f"Rs {med_val/1e7:.2f} Cr",
            "P10 Corpus": f"Rs {p10_val/1e7:.2f} Cr",
            "P90 Corpus": f"Rs {p90_val/1e7:.2f} Cr",
            "Monthly SWP": f"Rs {curr_swp:,.0f}",
            "Eff. Withdrawal Rate": f"{eff_rate:.1f}%",
            "Coverage (yrs)": f"{coverage:.1f}",
            "Survival Prob": f"{surv:.1f}%"
        })

    df_table = pd.DataFrame(table_data)
    st.dataframe(df_table, use_container_width=True, hide_index=True)

else:
    if not missing_inputs:
        st.info("Adjust the parameters in the sidebar and click RUN SIMULATION to begin.")
        st.markdown("""
        **What this simulator includes:**
        - Wealth Projection with P10, P25, P50, P75, P90 confidence bands
        - Drawdown Risk: peak-to-trough decline at median and stress percentiles
        - Asset Allocation Drift: how the portfolio mix evolves over time
        - Withdrawal Coverage Ratio: years of SWP remaining in the corpus
        - Effective Withdrawal Rate vs Blended Expected Return, year by year
        - Safe SWP Finder: binary search for maximum sustainable monthly withdrawal
        - Yearly table with P10/P90 range, coverage ratio, effective rate, and survival probability
        """)
