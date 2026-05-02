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
# FUND METADATA
# =========================
FUND_DEFAULTS = {
    "Large Cap":  {"color": "#00b0f6", "ret": 12.0, "vol": 16.0},
    "Flexi Cap":  {"color": "#00e676", "ret": 13.0, "vol": 18.0},
    "Mid Cap":    {"color": "#ffd600", "ret": 15.0, "vol": 22.0},
    "Small Cap":  {"color": "#ff6d00", "ret": 17.0, "vol": 28.0},
}
FUND_KEYS = list(FUND_DEFAULTS.keys())

# Full 4x4 base correlation (used to slice for active funds)
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
    run_btn = st.button("RUN SIMULATION", use_container_width=True, type="primary")

    st.divider()
    st.subheader("Investment & SWP")
    initial_investment = st.number_input(
        "Initial Investment (INR)",
        min_value=0, step=100000, value=None,
        placeholder="e.g. 1,00,000", format="%d"
    )
    monthly_withdrawal = st.number_input(
        "Monthly SWP (INR)",
        min_value=0, step=1000, value=None,
        placeholder="e.g. 10,000", format="%d"
    )

    st.subheader("Market Dynamics")
    years       = st.slider("Horizon (Years)", 5, 40, 20)
    simulations = st.slider("Simulations Count", 500, 10000, 2000, step=500)

    st.subheader("Inflation Settings")
    use_inflation      = st.checkbox("Inflation-Adjusted SWP", value=False)
    inflation_rate_val = st.slider("Annual Inflation (%)", 0.0, 12.0, 6.0)
    inflation_rate     = inflation_rate_val / 100

    # ── FUND SELECTION & USER-DEFINED PARAMETERS ─────────────────
    st.divider()
    st.subheader("Fund Selection & Parameters")
    st.caption("Tick the funds you invest in, then set their return, volatility, and DIP %.")

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
                    key=f"ret_{short}",
                    help="Expected annual return %"
                )
            with c2:
                fund_vol[fname] = st.number_input(
                    "Vol %", min_value=0.1, max_value=100.0,
                    value=fdef["vol"], step=0.5, format="%.1f",
                    key=f"vol_{short}",
                    help="Annual volatility (std dev) %"
                )
            with c3:
                fund_dip[fname] = st.number_input(
                    "DIP %", min_value=0.0, max_value=50.0,
                    value=0.0, step=0.5, format="%.1f",
                    key=f"dip_{short}",
                    help="First-year DIP drag %"
                )
        else:
            # Carry defaults so dict keys are always present
            fund_ret[fname] = fdef["ret"]
            fund_vol[fname] = fdef["vol"]
            fund_dip[fname] = 0.0

    # Derive active list
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
        # Fix rounding so it always sums to 100
        diff = 100 - sum(default_split.values())
        default_split[active_funds[0]] += diff

        c1, c2 = st.columns(2)
        with c1:
            st.caption("Initial Split")
            for f in active_funds:
                short = f.split()[0].lower()
                alloc_init[f] = st.number_input(
                    f"{f.split()[0]}", min_value=0, max_value=100,
                    value=default_split[f], format="%d",
                    key=f"ai_{short}"
                )
        with c2:
            st.caption("Withdrawal Split")
            for f in active_funds:
                short = f.split()[0].lower()
                alloc_withd[f] = st.number_input(
                    f"{f.split()[0]} ", min_value=0, max_value=100,
                    value=default_split[f], format="%d",
                    key=f"aw_{short}"
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

# Build numpy arrays for active funds only
n = len(active_funds)
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

# Slice correlation matrix to active funds
idx    = [FUND_KEYS.index(f) for f in active_funds]
corr_n = BASE_CORR[np.ix_(idx, idx)]
L      = np.linalg.cholesky(np.outer(mvol, mvol) * corr_n)


# =========================
# CORE SIMULATION
# =========================
def _simulate(w_override, show_progress=False):
    paths = np.zeros((simulations, months))
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

        port = initial_investment * alloc_arr.copy()
        for m in range(months):
            r = mret + (L @ np.random.normal(size=n))
            if m < 12:
                r += (dip_arr / 12) * (1 - m / 12)
            port *= (1 + r)

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

            paths[s, m] = np.sum(port)
            if paths[s, m] <= 0:
                break

    if show_progress:
        bar.empty()
        tdisp.empty()
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
    # Active fund summary bar
    st.markdown('<div class="section-header">Active Funds</div>', unsafe_allow_html=True)
    fcols = st.columns(n)
    for i, f in enumerate(active_funds):
        with fcols[i]:
            st.metric(
                f,
                f"{fund_ret[f]:.1f}% ret  |  {fund_vol[f]:.1f}% vol",
                f"DIP {fund_dip[f]:.1f}%  ·  Alloc {alloc_init[f]}%"
            )

    paths  = _simulate(monthly_withdrawal, show_progress=True)
    finals = paths[:, -1]
    p5, p10, p25, p50, p75, p90, p95 = np.percentile(paths, [5, 10, 25, 50, 75, 90, 95], axis=0)

    survival_prob   = np.mean(finals > 0) * 100
    survived_finals = finals[finals > 0]
    final_median    = np.median(survived_finals) if len(survived_finals) > 0 else 0
    ruined_count    = int(np.sum(finals <= 0))

    surviving_pct   = np.mean(paths > 0, axis=0)
    breakeven_month = next((m + 1 for m in range(months) if surviving_pct[m] < 0.5), None)

    running_max  = np.maximum.accumulate(paths, axis=1)
    drawdown     = (running_max - paths) / np.maximum(running_max, 1)
    p50_drawdown = np.percentile(drawdown, 50, axis=0) * 100
    p90_drawdown = np.percentile(drawdown, 90, axis=0) * 100

    annual_swp = monthly_withdrawal * 12
    wcr_median = p50 / annual_swp
    wcr_p10    = p10 / annual_swp
    wcr_p90    = p90 / annual_swp

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
    col2.metric("Median Final Corpus",  f"Rs {p50[-1]/1e7:.2f} Cr")
    col3.metric("P90 Corpus",           f"Rs {p90[-1]/1e7:.2f} Cr",
                help="Optimistic outcome — top 10% of scenarios")
    col4.metric("P10 Corpus",           f"Rs {p10[-1]/1e7:.2f} Cr",
                help="Stress outcome — bottom 10% of scenarios")

    col5, col6, col7, col8 = st.columns(4)
    col5.metric("Final Monthly SWP",
                f"Rs {int(monthly_withdrawal * ((1+inflation_rate)**(years-1) if use_inflation else 1)):,}")
    col6.metric("Total Withdrawn",      f"Rs {total_withdrawn/1e7:.2f} Cr")
    col7.metric("Portfolio Multiple",
                f"{final_median / initial_investment:.2f}x" if final_median > 0 else "0x")
    col8.metric("50% Survival Crossover",
                f"Month {breakeven_month}" if breakeven_month else f"Beyond {years} yrs")

    # ── RISK ANALYTICS ─────────────────────────────────────────────
    st.markdown('<div class="section-header">Risk Analytics</div>', unsafe_allow_html=True)

    rc1, rc2, rc3, rc4 = st.columns(4)
    rc1.metric("Median Corpus CAGR",       f"{median_cagr:.1f}% p.a.")
    rc2.metric("SWP Sustainability Index", f"{sustainability_idx:.2f}x",
               help="Blended return / SWP rate. >1 means returns can fund withdrawals.")
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
    else:
        headroom = annual_ret_blended * 100 - swp_rate
        insight = (
            f"Your SWP rate ({swp_rate:.1f}% p.a.) is below the blended expected return "
            f"({annual_ret_blended*100:.1f}% p.a.), leaving {headroom:.1f}% annual return as a reinvestment buffer."
        )
    st.markdown(f'<div class="insight-box">{insight}</div>', unsafe_allow_html=True)

    # ── CHART 1: WEALTH PROJECTION ─────────────────────────────────
    st.markdown('<div class="section-header">Wealth Projection Over Time</div>', unsafe_allow_html=True)

    fig1 = go.Figure()
    fig1.add_trace(go.Scatter(x=x_axis, y=p95/1e7, line=dict(color='rgba(0,176,246,0)'), showlegend=False, hoverinfo='skip'))
    fig1.add_trace(go.Scatter(x=x_axis, y=p5/1e7,  fill='tonexty', fillcolor='rgba(0,176,246,0.05)', line=dict(color='rgba(0,176,246,0)'), name="90% Confidence Band", hoverinfo='skip'))
    fig1.add_trace(go.Scatter(x=x_axis, y=p90/1e7, line=dict(color='rgba(0,176,246,0)'), showlegend=False, hoverinfo='skip'))
    fig1.add_trace(go.Scatter(x=x_axis, y=p10/1e7, fill='tonexty', fillcolor='rgba(0,176,246,0.13)', line=dict(color='rgba(0,176,246,0)'), name="80% Confidence Band", hoverinfo='skip'))
    fig1.add_trace(go.Scatter(x=x_axis, y=p75/1e7, line=dict(color='rgba(255,214,0,0)'), showlegend=False, hoverinfo='skip'))
    fig1.add_trace(go.Scatter(x=x_axis, y=p25/1e7, fill='tonexty', fillcolor='rgba(255,214,0,0.09)', line=dict(color='rgba(255,214,0,0)'), name="50% Confidence Band", hoverinfo='skip'))
    fig1.add_trace(go.Scatter(x=x_axis, y=p50/1e7, line=dict(color='#00b0f6', width=3), name="Median Projection"))
    fig1.add_trace(go.Scatter(x=x_axis, y=p90/1e7, line=dict(color='#00e676', width=1.5, dash='dot'), name="P90 (Optimistic)"))
    fig1.add_trace(go.Scatter(x=x_axis, y=p10/1e7, line=dict(color='#ff5252', width=1.5, dash='dot'), name="P10 (Stress)"))
    fig1.add_hline(y=0, line_color="red", line_dash="dash", line_width=1, annotation_text="Ruin Level")
    fig1.update_layout(hovermode="x unified", template="plotly_dark", height=480,
                       xaxis_title="Month", yaxis_title="Crores (INR)",
                       legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    st.plotly_chart(fig1, use_container_width=True)

    # ── CHART 2: DRAWDOWN ──────────────────────────────────────────
    st.markdown('<div class="section-header">Drawdown Risk Over Time</div>', unsafe_allow_html=True)
    st.caption("Peak-to-trough decline from the portfolio's all-time high. P90 = worst 10% of scenarios.")

    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=x_axis, y=p90_drawdown, fill='tozeroy', fillcolor='rgba(255,82,82,0.15)',
                              line=dict(color='#ff5252', width=2), name="P90 Drawdown (Stress)"))
    fig2.add_trace(go.Scatter(x=x_axis, y=p50_drawdown, fill='tozeroy', fillcolor='rgba(255,214,0,0.1)',
                              line=dict(color='#ffd600', width=2), name="Median Drawdown"))
    fig2.update_layout(template="plotly_dark", height=360, xaxis_title="Month",
                       yaxis_title="Drawdown from Peak (%)", legend=dict(orientation="h", y=1.05))
    st.plotly_chart(fig2, use_container_width=True)

    # ── CHART 3: ASSET DRIFT ───────────────────────────────────────
    st.markdown('<div class="section-header">Asset Allocation Drift (Representative Scenario)</div>', unsafe_allow_html=True)
    st.caption("How the portfolio mix evolves in a single seeded simulation.")

    fig3 = go.Figure()
    for i, (fname, color) in enumerate(zip(active_funds, colors_arr)):
        fig3.add_trace(go.Scatter(x=x_axis, y=asset_pct[:, i], stackgroup='one', name=fname, line=dict(color=color)))
    fig3.update_layout(template="plotly_dark", height=360, xaxis_title="Month",
                       yaxis_title="% of Portfolio", legend=dict(orientation="h", y=1.05))
    st.plotly_chart(fig3, use_container_width=True)

    # ── CHART 4: COVERAGE RATIO ────────────────────────────────────
    st.markdown('<div class="section-header">Withdrawal Coverage Ratio (Median)</div>', unsafe_allow_html=True)
    st.caption("Median corpus / annual SWP — years of withdrawals the portfolio can still fund. Below 10x = caution zone.")

    fig4 = go.Figure()
    fig4.add_trace(go.Scatter(x=x_axis, y=wcr_p90, line=dict(color='rgba(0,176,246,0)'), showlegend=False, hoverinfo='skip'))
    fig4.add_trace(go.Scatter(x=x_axis, y=wcr_p10, fill='tonexty', fillcolor='rgba(0,176,246,0.1)',
                              line=dict(color='rgba(0,176,246,0)'), name="P10–P90 Range", hoverinfo='skip'))
    fig4.add_trace(go.Scatter(x=x_axis, y=wcr_median, line=dict(color='#00e676', width=2.5), name="Median Coverage Ratio"))
    fig4.add_hline(y=10, line_color="#ffd600", line_dash="dash", annotation_text="10x (Caution Zone)")
    fig4.add_hline(y=1,  line_color="#ff5252", line_dash="dash", annotation_text="1x (Critical)")
    fig4.update_layout(template="plotly_dark", height=360, xaxis_title="Month",
                       yaxis_title="Years of SWP Remaining", legend=dict(orientation="h", y=1.05))
    st.plotly_chart(fig4, use_container_width=True)

    # ── CHART 5: EFFECTIVE WITHDRAWAL RATE ────────────────────────
    st.markdown('<div class="section-header">Effective Withdrawal Rate vs Blended Expected Return</div>', unsafe_allow_html=True)
    st.caption("Bars above the dashed line mean withdrawals are drawing down principal.")

    blended_pct          = annual_ret_blended * 100
    eff_withdrawal_rates = []
    for yr in range(1, years + 1):
        m_idx      = (yr * 12) - 1
        med_corpus = np.median(paths[:, m_idx])
        inf        = (1 + inflation_rate) ** (yr - 1) if use_inflation else 1
        curr_swp   = monthly_withdrawal * inf * 12
        eff_rate   = (curr_swp / med_corpus * 100) if med_corpus > 0 else 100
        eff_withdrawal_rates.append(eff_rate)

    bar_colors = ['#ff5252' if r > blended_pct else '#00b0f6' for r in eff_withdrawal_rates]
    fig5 = go.Figure()
    fig5.add_trace(go.Bar(x=yr_axis, y=eff_withdrawal_rates,
                          name="Effective Withdrawal Rate (%)", marker_color=bar_colors))
    fig5.add_hline(y=blended_pct, line_color="#ffd600", line_dash="dash",
                   annotation_text=f"Blended Expected Return: {blended_pct:.1f}%")
    fig5.update_layout(template="plotly_dark", height=360, xaxis_title="Year", yaxis_title="Rate (%)")
    st.plotly_chart(fig5, use_container_width=True)

    # ── SAFE SWP FINDER ───────────────────────────────────────────
    st.markdown('<div class="section-header">Safe Withdrawal Rate Finder</div>', unsafe_allow_html=True)

    with st.expander(f"Find Maximum SWP for {target_survival}% Survival Probability (click to run)"):
        st.info("Runs a binary search. Takes ~30–60 seconds depending on simulation count.")
        safe_swp = compute_safe_swp()
        st.success(
            f"For {target_survival}% survival over {years} years, "
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
                f"Your current SWP is conservative — you could withdraw up to "
                f"Rs {int(delta):,} more/month while maintaining {target_survival}% survival probability."
            )

    # ── YEARLY TABLE ──────────────────────────────────────────────
    st.markdown('<div class="section-header">Yearly Performance Summary (Median)</div>', unsafe_allow_html=True)

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
        table_data.append({
            "Year":                 yr,
            "Median Corpus":        f"Rs {med_val/1e7:.2f} Cr",
            "P10 Corpus":           f"Rs {p10_val/1e7:.2f} Cr",
            "P90 Corpus":           f"Rs {p90_val/1e7:.2f} Cr",
            "Monthly SWP":          f"Rs {curr_swp:,.0f}",
            "Eff. Withdrawal Rate": f"{eff_rate:.1f}%",
            "Coverage (yrs)":       f"{coverage:.1f}",
            "Survival Prob":        f"{surv:.1f}%"
        })

    st.dataframe(pd.DataFrame(table_data), use_container_width=True, hide_index=True)

else:
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
