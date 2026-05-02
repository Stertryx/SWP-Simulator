import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time

# =========================
# APP CONFIG
# =========================
st.set_page_config(page_title="Portfolio SWP Simulator", layout="wide")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'IBM Plex Sans', sans-serif;
    }
    .section-header {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.78rem;
        font-weight: 600;
        letter-spacing: 0.15em;
        text-transform: uppercase;
        color: #64b5f6;
        margin: 32px 0 8px 0;
        border-bottom: 1px solid #1a2744;
        padding-bottom: 8px;
    }
    .insight-box {
        background: linear-gradient(135deg, #0a1628 0%, #0d1f3c 100%);
        border-left: 3px solid #42a5f5;
        padding: 12px 18px;
        border-radius: 0 8px 8px 0;
        margin: 10px 0;
        font-size: 0.88rem;
        color: #b0bec5;
        line-height: 1.6;
    }
    .warn-box {
        background: linear-gradient(135deg, #1a0f00 0%, #2a1a00 100%);
        border-left: 3px solid #ffa726;
        padding: 12px 18px;
        border-radius: 0 8px 8px 0;
        margin: 10px 0;
        font-size: 0.88rem;
        color: #ffe0b2;
        line-height: 1.6;
    }
    .rebal-badge {
        background: #1a2744;
        border: 1px solid #42a5f5;
        border-radius: 4px;
        padding: 2px 8px;
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.72rem;
        color: #42a5f5;
        display: inline-block;
        margin-left: 8px;
    }
    .stButton > button {
        font-family: 'IBM Plex Mono', monospace !important;
        font-weight: 600 !important;
        letter-spacing: 0.1em !important;
    }
    div[data-testid="metric-container"] {
        background: #0a1628;
        border: 1px solid #1a2744;
        border-radius: 8px;
        padding: 12px 16px;
    }
</style>
""", unsafe_allow_html=True)

st.title("Portfolio Analytics: Fixed SWP Monte Carlo")
st.caption("Systematic Withdrawal Plan simulator · Monte Carlo engine · Annual rebalancing support")

# =========================
# FUND METADATA
# =========================
FUND_DEFAULTS = {
    "Large Cap":  {"color": "#42a5f5", "ret": 12.0, "vol": 16.0},
    "Flexi Cap":  {"color": "#66bb6a", "ret": 13.0, "vol": 18.0},
    "Mid Cap":    {"color": "#ffa726", "ret": 15.0, "vol": 22.0},
    "Small Cap":  {"color": "#ef5350", "ret": 17.0, "vol": 28.0},
}
FUND_KEYS = list(FUND_DEFAULTS.keys())

BASE_CORR = np.array([
    [1.0,  0.9,  0.8,  0.7],
    [0.9,  1.0,  0.85, 0.75],
    [0.8,  0.85, 1.0,  0.85],
    [0.7,  0.75, 0.85, 1.0]
])

# =========================
# SIDEBAR
# =========================
with st.sidebar:
    st.header("Simulation Control")
    run_btn = st.button("▶  RUN SIMULATION", use_container_width=True, type="primary")

    st.divider()
    st.subheader("Investment & SWP")
    initial_investment = st.number_input(
        "Initial Investment (INR)",
        min_value=0, step=100000, value=None,
        placeholder="e.g. 50,00,000", format="%d"
    )
    monthly_withdrawal = st.number_input(
        "Monthly SWP (INR)",
        min_value=0, step=1000, value=None,
        placeholder="e.g. 30,000", format="%d"
    )

    st.subheader("Market Dynamics")
    years       = st.slider("Horizon (Years)", 5, 40, 20)
    simulations = st.slider("Simulations Count", 500, 10000, 2000, step=500)

    st.subheader("Inflation Settings")
    use_inflation      = st.checkbox("Inflation-Adjusted SWP", value=False)
    inflation_rate_val = st.slider("Annual Inflation (%)", 0.0, 12.0, 6.0)
    inflation_rate     = inflation_rate_val / 100

    # ── REBALANCING ──────────────────────────────────────────────
    st.divider()
    st.subheader("Rebalancing")
    enable_rebalancing = st.checkbox("Annual Rebalancing", value=False,
        help="Reset fund weights to initial allocation every 12 months — simulates a disciplined investor.")
    if enable_rebalancing:
        st.markdown('<span class="rebal-badge">ACTIVE · Every 12 months</span>', unsafe_allow_html=True)
        st.caption("At month-end of each year, the portfolio is rebalanced back to the initial allocation split. This forces systematic sell-high/buy-low behaviour.")

    # ── FUND SELECTION & PARAMETERS ─────────────────────────────
    st.divider()
    st.subheader("Fund Selection & Parameters")
    st.caption("Select funds, set return, volatility, and first-year DIP %.")

    fund_active = {}
    fund_ret    = {}
    fund_vol    = {}
    fund_dip    = {}

    for fname, fdef in FUND_DEFAULTS.items():
        short   = fname.split()[0].lower()
        checked = st.checkbox(f"**{fname}**", value=True, key=f"chk_{short}")
        fund_active[fname] = checked

        if checked:
            c1, c2, c3 = st.columns(3)
            with c1:
                fund_ret[fname] = st.number_input(
                    "Ret %", min_value=0.0, max_value=60.0,
                    value=fdef["ret"], step=0.5, format="%.1f",
                    key=f"ret_{short}", help="Expected annual return %"
                )
            with c2:
                fund_vol[fname] = st.number_input(
                    "Vol %", min_value=0.1, max_value=100.0,
                    value=fdef["vol"], step=0.5, format="%.1f",
                    key=f"vol_{short}", help="Annual volatility (std dev) %"
                )
            with c3:
                fund_dip[fname] = st.number_input(
                    "DIP %", min_value=0.0, max_value=50.0,
                    value=0.0, step=0.5, format="%.1f",
                    key=f"dip_{short}", help="First-year DIP drag %"
                )
        else:
            fund_ret[fname] = fdef["ret"]
            fund_vol[fname] = fdef["vol"]
            fund_dip[fname] = 0.0

    active_funds = [f for f in FUND_KEYS if fund_active[f]]

    if not active_funds:
        st.error("Please select at least one fund.")
        st.stop()

    # ── ALLOCATION ────────────────────────────────────────────────
    st.divider()
    st.subheader("Asset Allocation (%)")

    alloc_init  = {}
    alloc_withd = {}

    if len(active_funds) == 1:
        alloc_init[active_funds[0]]  = 100
        alloc_withd[active_funds[0]] = 100
        st.info(f"Single fund — 100% allocated to {active_funds[0]}.")
    else:
        default_split = {f: round(100 / len(active_funds)) for f in active_funds}
        diff = 100 - sum(default_split.values())
        default_split[active_funds[0]] += diff

        c1, c2 = st.columns(2)
        with c1:
            st.caption("Initial Split")
            for f in active_funds:
                short = f.split()[0].lower()
                alloc_init[f] = st.number_input(
                    f"{f.split()[0]}", min_value=0, max_value=100,
                    value=default_split[f], format="%d", key=f"ai_{short}"
                )
        with c2:
            st.caption("Withdrawal Split")
            for f in active_funds:
                short = f.split()[0].lower()
                alloc_withd[f] = st.number_input(
                    f"{f.split()[0]} ", min_value=0, max_value=100,
                    value=default_split[f], format="%d", key=f"aw_{short}"
                )

    # ── SAFE SWP ──────────────────────────────────────────────────
    st.divider()
    st.subheader("Safe SWP Finder")
    target_survival = st.slider("Target Survival Probability (%)", 70, 99, 90)


# =========================
# VALIDATION
# =========================
missing_inputs = []
if initial_investment is None:
    missing_inputs.append("Initial Investment")
if monthly_withdrawal is None:
    missing_inputs.append("Monthly SWP")

if missing_inputs:
    st.info("Configure parameters in the sidebar and click RUN SIMULATION.")
    st.markdown(f"**Please fill in:** {', '.join(missing_inputs)}")
    st.markdown("""
    **What this simulator includes:**
    - Wealth Projection: P10 / P25 / P50 / P75 / P90 confidence bands
    - **Annual Rebalancing** toggle — disciplined investor vs. drift
    - Drawdown Risk: peak-to-trough at median and stress percentiles
    - **Max Annual Drawdown by percentile** (P10 / P50 / P90) per year
    - Asset Allocation Drift in a representative scenario
    - Withdrawal Coverage Ratio: years of SWP remaining in corpus
    - Effective Withdrawal Rate vs. Blended Expected Return
    - Safe SWP Finder: binary search for maximum sustainable monthly withdrawal
    - Yearly table with P10/P90 range, coverage ratio, effective rate, survival probability
    """)
    st.stop()

n           = len(active_funds)
alloc_arr   = np.array([alloc_init[f]  / 100 for f in active_funds])
w_alloc_arr = np.array([alloc_withd[f] / 100 for f in active_funds])
returns_arr = np.array([fund_ret[f]    / 100 for f in active_funds])
vols_arr    = np.array([fund_vol[f]    / 100 for f in active_funds])
dip_arr     = np.array([fund_dip[f]    / 100 for f in active_funds])
colors_arr  = [FUND_DEFAULTS[f]["color"] for f in active_funds]

if not np.isclose(sum(alloc_init.values()), 100):
    st.error(f"Initial Split sums to {sum(alloc_init.values())}% — must equal 100%.")
    st.stop()
if not np.isclose(sum(alloc_withd.values()), 100):
    st.error(f"Withdrawal Split sums to {sum(alloc_withd.values())}% — must equal 100%.")
    st.stop()

# =========================
# ENGINE CONSTANTS
# =========================
months  = years * 12
mret    = (1 + returns_arr) ** (1 / 12) - 1
mvol    = vols_arr / np.sqrt(12)

idx    = [FUND_KEYS.index(f) for f in active_funds]
corr_n = BASE_CORR[np.ix_(idx, idx)]
L      = np.linalg.cholesky(np.outer(mvol, mvol) * corr_n)


# =========================
# REBALANCING HELPER
# =========================
def _rebalance(port, target_alloc):
    """Rebalance portfolio to target allocation weights."""
    total = np.sum(port)
    if total > 0:
        port[:] = total * target_alloc
    return port


# =========================
# CORE SIMULATION
# =========================
def _simulate(w_override, show_progress=False, track_annual_drawdown=False):
    """
    Run Monte Carlo simulation.
    Returns paths (simulations x months).
    If track_annual_drawdown=True, also returns annual_dd (simulations x years).
    """
    paths      = np.zeros((simulations, months))
    annual_dd  = np.zeros((simulations, years)) if track_annual_drawdown else None

    bar   = st.progress(0, text="Simulating scenarios…") if show_progress else None
    tdisp = st.empty() if show_progress else None
    t0    = time.time() if show_progress else None

    for s in range(simulations):
        if show_progress and s % 100 == 0:
            pct = (s + 1) / simulations
            bar.progress(pct)
            elapsed = time.time() - t0
            if s > 0:
                rem = (elapsed / s) * (simulations - s)
                tdisp.caption(f"Estimated time remaining: {rem:.1f}s")

        port      = initial_investment * alloc_arr.copy()
        yr_peak   = np.sum(port)   # for annual drawdown tracking
        yr_trough = np.sum(port)

        for m in range(months):
            r = mret + (L @ np.random.normal(size=n))
            if m < 12:
                r += (dip_arr / 12) * (1 - m / 12)
            port *= (1 + r)

            # ── Annual rebalancing ──────────────────────────────────
            if enable_rebalancing and (m + 1) % 12 == 0 and m < months - 1:
                port = _rebalance(port, alloc_arr)

            # ── Withdrawal ─────────────────────────────────────────
            inf     = (1 + inflation_rate) ** (m // 12) if use_inflation else 1
            w_total = w_override * inf
            req     = w_total * w_alloc_arr

            for i in range(n):
                if port[i] >= req[i]:
                    port[i] -= req[i]
                else:
                    shortfall = req[i] - port[i]
                    port[i]   = 0
                    for j in range(n):
                        if port[j] > 0:
                            take      = min(port[j], shortfall)
                            port[j]  -= take
                            shortfall -= take
                        if shortfall <= 0:
                            break

            total_val      = np.sum(port)
            paths[s, m]    = total_val

            # ── Track annual max drawdown ───────────────────────────
            if track_annual_drawdown:
                yr_idx = m // 12
                if m % 12 == 0:
                    yr_peak   = total_val
                    yr_trough = total_val
                else:
                    if total_val > yr_peak:
                        yr_peak = total_val
                    if total_val < yr_trough:
                        yr_trough = total_val
                if (m + 1) % 12 == 0 or m == months - 1:
                    dd = (yr_peak - yr_trough) / yr_peak * 100 if yr_peak > 0 else 0
                    if yr_idx < years:
                        annual_dd[s, yr_idx] = dd

            if total_val <= 0:
                break

    if show_progress:
        bar.empty()
        tdisp.empty()

    if track_annual_drawdown:
        return paths, annual_dd
    return paths


def compute_safe_swp():
    lo, hi = 1000, monthly_withdrawal * 3
    for _ in range(12):
        mid  = (lo + hi) / 2
        surv = np.mean(_simulate(mid)[:, -1] > 0) * 100
        if surv >= target_survival:
            lo = mid
        else:
            hi = mid
    return lo


def run_asset_tracking():
    np.random.seed(42)
    port          = initial_investment * alloc_arr.copy()
    asset_history = np.zeros((months, n))

    for m in range(months):
        r = mret + (L @ np.random.normal(size=n))
        if m < 12:
            r += (dip_arr / 12) * (1 - m / 12)
        port *= (1 + r)

        if enable_rebalancing and (m + 1) % 12 == 0 and m < months - 1:
            port = _rebalance(port, alloc_arr)

        inf     = (1 + inflation_rate) ** (m // 12) if use_inflation else 1
        w_total = monthly_withdrawal * inf
        req     = w_total * w_alloc_arr

        for i in range(n):
            if port[i] >= req[i]:
                port[i] -= req[i]
            else:
                shortfall = req[i] - port[i]
                port[i]   = 0
                for j in range(n):
                    if port[j] > 0:
                        take      = min(port[j], shortfall)
                        port[j]  -= take
                        shortfall -= take
                    if shortfall <= 0:
                        break

        asset_history[m] = port.copy()
        if np.sum(port) <= 0:
            break
    return asset_history


# =========================
# RUN & DISPLAY
# =========================
if run_btn:
    # ── Active fund summary ────────────────────────────────────────
    st.markdown('<div class="section-header">Active Funds</div>', unsafe_allow_html=True)
    if enable_rebalancing:
        st.markdown(
            '**Rebalancing Mode:** Annual (every 12 months) &nbsp;<span class="rebal-badge">ON</span>',
            unsafe_allow_html=True
        )
    fcols = st.columns(n)
    for i, f in enumerate(active_funds):
        with fcols[i]:
            st.metric(
                f,
                f"{fund_ret[f]:.1f}% ret  |  {fund_vol[f]:.1f}% vol",
                f"DIP {fund_dip[f]:.1f}%  ·  Alloc {alloc_init[f]}%"
            )

    paths, annual_dd = _simulate(monthly_withdrawal, show_progress=True, track_annual_drawdown=True)
    finals = paths[:, -1]
    p5, p10, p25, p50, p75, p90, p95 = np.percentile(paths, [5, 10, 25, 50, 75, 90, 95], axis=0)

    survival_prob   = np.mean(finals > 0) * 100
    survived_finals = finals[finals > 0]
    final_median    = np.median(survived_finals) if len(survived_finals) > 0 else 0
    ruined_count    = int(np.sum(finals <= 0))

    surviving_pct   = np.mean(paths > 0, axis=0)
    breakeven_month = next((m + 1 for m in range(months) if surviving_pct[m] < 0.5), None)

    # Drawdown (cumulative)
    running_max  = np.maximum.accumulate(paths, axis=1)
    drawdown     = (running_max - paths) / np.maximum(running_max, 1)
    p50_drawdown = np.percentile(drawdown, 50, axis=0) * 100
    p90_drawdown = np.percentile(drawdown, 90, axis=0) * 100

    # Annual max drawdown percentiles
    ann_dd_p10 = np.percentile(annual_dd, 10, axis=0)
    ann_dd_p50 = np.percentile(annual_dd, 50, axis=0)
    ann_dd_p90 = np.percentile(annual_dd, 90, axis=0)

    annual_swp     = monthly_withdrawal * 12
    wcr_median     = p50 / annual_swp
    wcr_p10        = p10 / annual_swp
    wcr_p90        = p90 / annual_swp

    annual_ret_blended = float(np.dot(alloc_arr, returns_arr))
    swp_rate           = (monthly_withdrawal * 12) / initial_investment * 100
    median_cagr        = ((p50[-1] / initial_investment) ** (1 / years) - 1) * 100 if p50[-1] > 0 else 0
    upside_downside    = (p90[-1] / p10[-1]) if p10[-1] > 0 else float('inf')

    ruin_months = []
    for s in range(simulations):
        for m in range(months):
            if paths[s, m] <= 0:
                ruin_months.append(m + 1)
                break
    avg_ruin_month     = int(np.mean(ruin_months)) if ruin_months else None
    sustainability_idx = (annual_ret_blended * 100) / swp_rate if swp_rate > 0 else float('inf')
    total_withdrawn    = sum(
        monthly_withdrawal * ((1 + inflation_rate) ** (m // 12) if use_inflation else 1)
        for m in range(months)
    )

    asset_history = run_asset_tracking()
    asset_totals  = asset_history.sum(axis=1)
    asset_pct     = np.where(asset_totals[:, None] > 0, asset_history / asset_totals[:, None] * 100, 0)

    x_axis = list(range(1, months + 1))
    yr_axis = list(range(1, years + 1))

    # ── CORE RESULTS ───────────────────────────────────────────────
    st.divider()
    st.markdown('<div class="section-header">Core Results</div>', unsafe_allow_html=True)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Survival Probability", f"{survival_prob:.1f}%",
                help="% of simulations where corpus outlasted the full horizon")
    col2.metric("Median Final Corpus",  f"₹{p50[-1]/1e7:.2f} Cr")
    col3.metric("P90 Corpus",           f"₹{p90[-1]/1e7:.2f} Cr",
                help="Optimistic outcome — top 10% of scenarios")
    col4.metric("P10 Corpus",           f"₹{p10[-1]/1e7:.2f} Cr",
                help="Stress outcome — bottom 10% of scenarios")

    col5, col6, col7, col8 = st.columns(4)
    col5.metric("Final Monthly SWP",
                f"₹{int(monthly_withdrawal * ((1+inflation_rate)**(years-1) if use_inflation else 1)):,}")
    col6.metric("Total Withdrawn",   f"₹{total_withdrawn/1e7:.2f} Cr")
    col7.metric("Portfolio Multiple",
                f"{final_median / initial_investment:.2f}x" if final_median > 0 else "0x")
    col8.metric("50% Survival Crossover",
                f"Month {breakeven_month}" if breakeven_month else f"Beyond {years} yrs")

    # ── RISK ANALYTICS ─────────────────────────────────────────────
    st.markdown('<div class="section-header">Risk Analytics</div>', unsafe_allow_html=True)

    rc1, rc2, rc3, rc4 = st.columns(4)
    rc1.metric("Median Corpus CAGR",       f"{median_cagr:.1f}% p.a.")
    rc2.metric("SWP Sustainability Index", f"{sustainability_idx:.2f}x",
               help="Blended return / SWP rate. >1 means returns fund withdrawals.")
    rc3.metric("Upside / Downside Ratio",
               f"{upside_downside:.1f}x" if upside_downside != float('inf') else "N/A",
               help="P90 / P10 final corpus. Higher = more outcome uncertainty.")
    rc4.metric("Avg Month of Ruin (Failed)",
               f"Month {avg_ruin_month}" if avg_ruin_month else "No failures")

    if swp_rate > annual_ret_blended * 100:
        insight = (
            f"Your SWP rate ({swp_rate:.1f}% p.a.) exceeds the blended expected portfolio return "
            f"({annual_ret_blended*100:.1f}% p.a.). The corpus will erode over time in most scenarios. "
            f"Consider reducing the monthly withdrawal or shifting to higher-return funds."
        )
        st.markdown(f'<div class="warn-box">⚠ {insight}</div>', unsafe_allow_html=True)
    else:
        headroom = annual_ret_blended * 100 - swp_rate
        insight = (
            f"Your SWP rate ({swp_rate:.1f}% p.a.) is below the blended expected return "
            f"({annual_ret_blended*100:.1f}% p.a.), leaving {headroom:.1f}% annual return as a reinvestment buffer."
        )
        st.markdown(f'<div class="insight-box">✓ {insight}</div>', unsafe_allow_html=True)

    if enable_rebalancing:
        st.markdown(
            '<div class="insight-box">🔄 <strong>Annual Rebalancing Active</strong> — Portfolio weights are reset to '
            'initial allocation at the end of each year. This enforces sell-high/buy-low discipline, '
            'reduces allocation drift, and typically lowers tail risk at the cost of some upside in trending markets.</div>',
            unsafe_allow_html=True
        )

    # ── CHART 1: WEALTH PROJECTION ─────────────────────────────────
    st.markdown('<div class="section-header">Wealth Projection Over Time</div>', unsafe_allow_html=True)

    fig1 = go.Figure()
    fig1.add_trace(go.Scatter(x=x_axis, y=p95/1e7, line=dict(color='rgba(66,165,245,0)'), showlegend=False, hoverinfo='skip'))
    fig1.add_trace(go.Scatter(x=x_axis, y=p5/1e7,  fill='tonexty', fillcolor='rgba(66,165,245,0.05)', line=dict(color='rgba(66,165,245,0)'), name="90% Band", hoverinfo='skip'))
    fig1.add_trace(go.Scatter(x=x_axis, y=p90/1e7, line=dict(color='rgba(66,165,245,0)'), showlegend=False, hoverinfo='skip'))
    fig1.add_trace(go.Scatter(x=x_axis, y=p10/1e7, fill='tonexty', fillcolor='rgba(66,165,245,0.12)', line=dict(color='rgba(66,165,245,0)'), name="80% Band", hoverinfo='skip'))
    fig1.add_trace(go.Scatter(x=x_axis, y=p75/1e7, line=dict(color='rgba(255,167,38,0)'), showlegend=False, hoverinfo='skip'))
    fig1.add_trace(go.Scatter(x=x_axis, y=p25/1e7, fill='tonexty', fillcolor='rgba(255,167,38,0.08)', line=dict(color='rgba(255,167,38,0)'), name="50% Band", hoverinfo='skip'))
    fig1.add_trace(go.Scatter(x=x_axis, y=p50/1e7, line=dict(color='#42a5f5', width=3), name="Median (P50)"))
    fig1.add_trace(go.Scatter(x=x_axis, y=p90/1e7, line=dict(color='#66bb6a', width=1.5, dash='dot'), name="P90 Optimistic"))
    fig1.add_trace(go.Scatter(x=x_axis, y=p10/1e7, line=dict(color='#ef5350', width=1.5, dash='dot'), name="P10 Stress"))

    if enable_rebalancing:
        for yr in range(1, years):
            fig1.add_vline(x=yr * 12, line_color="rgba(66,165,245,0.2)", line_width=1, line_dash="dot")

    fig1.add_hline(y=0, line_color="#ef5350", line_dash="dash", line_width=1, annotation_text="Ruin Level")
    fig1.update_layout(
        hovermode="x unified", template="plotly_dark", height=480,
        xaxis_title="Month", yaxis_title="Crores (INR)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(10,22,40,0.8)'
    )
    if enable_rebalancing:
        fig1.add_annotation(
            x=12, y=p90[11]/1e7, text="↕ Rebalance", showarrow=False,
            font=dict(color="#42a5f5", size=10), xanchor="left"
        )
    st.plotly_chart(fig1, use_container_width=True)

    # ── CHART 2: DRAWDOWN + MAX ANNUAL DRAWDOWN ─────────────────────
    st.markdown('<div class="section-header">Drawdown Risk</div>', unsafe_allow_html=True)
    st.caption("Left: cumulative peak-to-trough drawdown. Right: worst single-year drawdown by percentile.")

    # Summary stat cards for overall drawdown percentiles
    avg_ann_dd_p10 = float(np.mean(ann_dd_p10))
    avg_ann_dd_p50 = float(np.mean(ann_dd_p50))
    avg_ann_dd_p90 = float(np.mean(ann_dd_p90))
    worst_ann_dd_p10 = float(np.max(ann_dd_p10))
    worst_ann_dd_p50 = float(np.max(ann_dd_p50))
    worst_ann_dd_p90 = float(np.max(ann_dd_p90))
    max_cum_dd_p50 = float(np.max(p50_drawdown))
    max_cum_dd_p90 = float(np.max(p90_drawdown))

    dd_c1, dd_c2, dd_c3, dd_c4 = st.columns(4)
    dd_c1.metric(
        "Avg Annual DD · Median",
        f"{avg_ann_dd_p50:.1f}%",
        f"Peak year: {worst_ann_dd_p50:.1f}%",
        delta_color="inverse",
        help="Average of median max-drawdown across all years"
    )
    dd_c2.metric(
        "Avg Annual DD · P90 Stress",
        f"{avg_ann_dd_p90:.1f}%",
        f"Peak year: {worst_ann_dd_p90:.1f}%",
        delta_color="inverse",
        help="Average of P90 max-drawdown across all years — worst 10% of scenarios"
    )
    dd_c3.metric(
        "Max Cumulative DD · Median",
        f"{max_cum_dd_p50:.1f}%",
        help="Largest peak-to-trough decline in the median scenario across the full horizon"
    )
    dd_c4.metric(
        "Max Cumulative DD · P90",
        f"{max_cum_dd_p90:.1f}%",
        help="Largest peak-to-trough decline in the P90 stress scenario"
    )

    st.markdown(
        f'<div class="insight-box">'
        f'<strong>Drawdown Summary</strong> &nbsp;|&nbsp; '
        f'P10 avg annual drawdown: <strong>{avg_ann_dd_p10:.1f}%</strong> &nbsp;·&nbsp; '
        f'Median: <strong>{avg_ann_dd_p50:.1f}%</strong> &nbsp;·&nbsp; '
        f'P90 stress: <strong>{avg_ann_dd_p90:.1f}%</strong>. '
        f'Worst single year in median scenario: <strong>{worst_ann_dd_p50:.1f}%</strong>; '
        f'in P90 stress: <strong>{worst_ann_dd_p90:.1f}%</strong>.'
        f'</div>',
        unsafe_allow_html=True
    )

    col_dd1, col_dd2 = st.columns(2)

    with col_dd1:
        fig2a = go.Figure()
        fig2a.add_trace(go.Scatter(
            x=x_axis, y=p90_drawdown, fill='tozeroy', fillcolor='rgba(239,83,80,0.12)',
            line=dict(color='#ef5350', width=2), name="P90 (Stress)"
        ))
        fig2a.add_trace(go.Scatter(
            x=x_axis, y=p50_drawdown, fill='tozeroy', fillcolor='rgba(255,167,38,0.08)',
            line=dict(color='#ffa726', width=2), name="Median"
        ))
        fig2a.update_layout(
            template="plotly_dark", height=340, title="Cumulative Drawdown from Peak",
            xaxis_title="Month", yaxis_title="Drawdown (%)",
            legend=dict(orientation="h", y=1.05),
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(10,22,40,0.8)'
        )
        st.plotly_chart(fig2a, use_container_width=True)

    with col_dd2:
        fig2b = go.Figure()
        fig2b.add_trace(go.Bar(
            x=yr_axis, y=ann_dd_p90,
            name="P90 (Worst 10%)", marker_color='rgba(239,83,80,0.75)',
            marker_line_color='#ef5350', marker_line_width=1
        ))
        fig2b.add_trace(go.Bar(
            x=yr_axis, y=ann_dd_p50,
            name="Median", marker_color='rgba(255,167,38,0.75)',
            marker_line_color='#ffa726', marker_line_width=1
        ))
        fig2b.add_trace(go.Bar(
            x=yr_axis, y=ann_dd_p10,
            name="P10 (Best 10%)", marker_color='rgba(102,187,106,0.75)',
            marker_line_color='#66bb6a', marker_line_width=1
        ))
        fig2b.update_layout(
            template="plotly_dark", height=340, barmode='group',
            title="Max Annual Drawdown by Year",
            xaxis_title="Year", yaxis_title="Max Drawdown in Year (%)",
            legend=dict(orientation="h", y=1.05),
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(10,22,40,0.8)'
        )
        st.plotly_chart(fig2b, use_container_width=True)

    # ── CHART 3: ASSET DRIFT ───────────────────────────────────────
    st.markdown('<div class="section-header">Asset Allocation Drift (Representative Scenario)</div>', unsafe_allow_html=True)
    rebal_note = " Vertical steps show annual rebalancing events." if enable_rebalancing else " No rebalancing — weights drift with market returns."
    st.caption(f"Single seeded simulation.{rebal_note}")

    fig3 = go.Figure()
    for i, (fname, color) in enumerate(zip(active_funds, colors_arr)):
        fig3.add_trace(go.Scatter(
            x=x_axis, y=asset_pct[:, i],
            stackgroup='one', name=fname, line=dict(color=color)
        ))
    if enable_rebalancing:
        for yr in range(1, years):
            fig3.add_vline(x=yr * 12, line_color="rgba(255,255,255,0.2)", line_width=1, line_dash="dot")
    fig3.update_layout(
        template="plotly_dark", height=340, xaxis_title="Month",
        yaxis_title="% of Portfolio", legend=dict(orientation="h", y=1.05),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(10,22,40,0.8)'
    )
    st.plotly_chart(fig3, use_container_width=True)

    # ── CHART 4: COVERAGE RATIO ────────────────────────────────────
    st.markdown('<div class="section-header">Withdrawal Coverage Ratio</div>', unsafe_allow_html=True)
    st.caption("Median corpus ÷ annual SWP = years of withdrawals remaining. Below 10× is caution zone.")

    fig4 = go.Figure()
    fig4.add_trace(go.Scatter(x=x_axis, y=wcr_p90, line=dict(color='rgba(66,165,245,0)'), showlegend=False, hoverinfo='skip'))
    fig4.add_trace(go.Scatter(
        x=x_axis, y=wcr_p10, fill='tonexty', fillcolor='rgba(66,165,245,0.08)',
        line=dict(color='rgba(66,165,245,0)'), name="P10–P90 Range", hoverinfo='skip'
    ))
    fig4.add_trace(go.Scatter(
        x=x_axis, y=wcr_median, line=dict(color='#66bb6a', width=2.5), name="Median Coverage"
    ))
    fig4.add_hline(y=10, line_color="#ffa726", line_dash="dash", annotation_text="10× Caution Zone")
    fig4.add_hline(y=1,  line_color="#ef5350", line_dash="dash", annotation_text="1× Critical")
    fig4.update_layout(
        template="plotly_dark", height=360, xaxis_title="Month",
        yaxis_title="Years of SWP Remaining", legend=dict(orientation="h", y=1.05),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(10,22,40,0.8)'
    )
    st.plotly_chart(fig4, use_container_width=True)

    # ── CHART 5: EFFECTIVE WITHDRAWAL RATE ────────────────────────
    st.markdown('<div class="section-header">Effective Withdrawal Rate vs Blended Expected Return</div>', unsafe_allow_html=True)
    st.caption("Red bars = withdrawals are drawing down principal. Green = returns are covering the SWP.")

    blended_pct          = annual_ret_blended * 100
    eff_withdrawal_rates = []
    for yr in range(1, years + 1):
        m_idx      = (yr * 12) - 1
        med_corpus = np.median(paths[:, m_idx])
        inf        = (1 + inflation_rate) ** (yr - 1) if use_inflation else 1
        curr_swp   = monthly_withdrawal * inf * 12
        eff_rate   = (curr_swp / med_corpus * 100) if med_corpus > 0 else 100
        eff_withdrawal_rates.append(eff_rate)

    bar_colors = ['#ef5350' if r > blended_pct else '#66bb6a' for r in eff_withdrawal_rates]
    fig5 = go.Figure()
    fig5.add_trace(go.Bar(
        x=yr_axis, y=eff_withdrawal_rates,
        name="Effective Withdrawal Rate (%)",
        marker_color=bar_colors,
        marker_line_color='rgba(255,255,255,0.1)',
        marker_line_width=1
    ))
    fig5.add_hline(
        y=blended_pct, line_color="#ffa726", line_dash="dash",
        annotation_text=f"Blended Expected Return: {blended_pct:.1f}%"
    )
    fig5.update_layout(
        template="plotly_dark", height=360, xaxis_title="Year", yaxis_title="Rate (%)",
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(10,22,40,0.8)'
    )
    st.plotly_chart(fig5, use_container_width=True)

    # ── CHART 6: SURVIVAL PROBABILITY DECAY ───────────────────────
    st.markdown('<div class="section-header">Survival Probability Decay</div>', unsafe_allow_html=True)
    st.caption("% of simulations still alive (corpus > 0) at each month. Shows how quickly your safety margin erodes.")

    fig6 = go.Figure()
    fig6.add_trace(go.Scatter(
        x=x_axis, y=surviving_pct * 100,
        fill='tozeroy', fillcolor='rgba(66,165,245,0.1)',
        line=dict(color='#42a5f5', width=2.5), name="Survival %"
    ))
    fig6.add_hline(y=90, line_color="#66bb6a", line_dash="dot", annotation_text="90%")
    fig6.add_hline(y=75, line_color="#ffa726", line_dash="dot", annotation_text="75%")
    fig6.add_hline(y=50, line_color="#ef5350", line_dash="dot", annotation_text="50%")
    fig6.update_layout(
        template="plotly_dark", height=320, xaxis_title="Month",
        yaxis_title="% of Simulations Surviving", yaxis=dict(range=[0, 102]),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(10,22,40,0.8)'
    )
    st.plotly_chart(fig6, use_container_width=True)

    # ── SAFE SWP FINDER ───────────────────────────────────────────
    st.markdown('<div class="section-header">Safe Withdrawal Rate Finder</div>', unsafe_allow_html=True)

    with st.expander(f"Find Maximum SWP for {target_survival}% Survival Probability (click to run)"):
        st.info("Runs a binary search across 12 iterations. Takes ~30–60 seconds.")
        safe_swp = compute_safe_swp()
        st.success(
            f"For {target_survival}% survival over {years} years, "
            f"the safe monthly SWP is approximately ₹{int(safe_swp):,}"
        )
        if safe_swp < monthly_withdrawal:
            delta = monthly_withdrawal - safe_swp
            st.warning(
                f"Your current SWP of ₹{monthly_withdrawal:,} exceeds the safe level by "
                f"₹{int(delta):,}/month ({delta/safe_swp*100:.1f}%). "
                f"Consider reducing the withdrawal or accepting a lower survival target."
            )
        else:
            delta = safe_swp - monthly_withdrawal
            st.success(
                f"Your current SWP is conservative — you could withdraw up to "
                f"₹{int(delta):,} more/month while maintaining {target_survival}% survival probability."
            )

    # ── YEARLY TABLE ──────────────────────────────────────────────
    st.markdown('<div class="section-header">Yearly Performance Summary</div>', unsafe_allow_html=True)

    table_data = []
    for yr in range(1, years + 1):
        m_idx    = (yr * 12) - 1
        surv     = np.mean(paths[:, m_idx] > 0) * 100
        med_val  = np.median(paths[:, m_idx])
        p10_val  = np.percentile(paths[:, m_idx], 10)
        p90_val  = np.percentile(paths[:, m_idx], 90)
        curr_swp = monthly_withdrawal * ((1 + inflation_rate) ** (yr - 1) if use_inflation else 1)
        eff_rate = (curr_swp * 12 / med_val * 100) if med_val > 0 else float('inf')
        coverage = (med_val / (curr_swp * 12)) if curr_swp > 0 else 0
        max_dd_p50 = ann_dd_p50[yr - 1]
        max_dd_p90 = ann_dd_p90[yr - 1]
        table_data.append({
            "Year":                  yr,
            "Median Corpus":         f"₹{med_val/1e7:.2f} Cr",
            "P10 Corpus":            f"₹{p10_val/1e7:.2f} Cr",
            "P90 Corpus":            f"₹{p90_val/1e7:.2f} Cr",
            "Monthly SWP":           f"₹{curr_swp:,.0f}",
            "Eff. Withdrawal Rate":  f"{eff_rate:.1f}%",
            "Coverage (yrs)":        f"{coverage:.1f}",
            "Max DD (Median)":       f"{max_dd_p50:.1f}%",
            "Max DD (P90 Stress)":   f"{max_dd_p90:.1f}%",
            "Survival Prob":         f"{surv:.1f}%"
        })

    st.dataframe(pd.DataFrame(table_data), use_container_width=True, hide_index=True)

else:
    st.info("Configure parameters in the sidebar and click **▶ RUN SIMULATION** to begin.")
    st.markdown("""
    **What this simulator includes:**
    - Wealth Projection: P10 / P25 / P50 / P75 / P90 confidence bands
    - **Annual Rebalancing** toggle — disciplined investor vs. drift simulation
    - Drawdown Risk: cumulative peak-to-trough at median and stress percentiles
    - **Max Annual Drawdown** by percentile (P10 / P50 / P90) — per year bar chart
    - Asset Allocation Drift with rebalancing markers
    - Withdrawal Coverage Ratio: years of SWP remaining in corpus
    - Survival Probability Decay curve
    - Effective Withdrawal Rate vs. Blended Expected Return
    - Safe SWP Finder: binary search for maximum sustainable monthly withdrawal
    - Yearly table with P10/P90 range, coverage ratio, max drawdown, and survival probability
    """)
