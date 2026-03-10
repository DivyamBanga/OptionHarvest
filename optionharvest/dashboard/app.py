"""
OptionHarvest Dashboard

One page to see everything and control the bot.
Run with: streamlit run optionharvest/dashboard/app.py
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import streamlit as st
import yaml

# ---------------------------------------------------------------------------
# Page config -- must be first Streamlit call
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="OptionHarvest",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS -- minimal, flat, no AI template look
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    /* Tighten spacing */
    .block-container { padding-top: 1.5rem; padding-bottom: 1rem; }

    /* Remove default streamlit header/footer */
    #MainMenu { visibility: hidden; }
    header { visibility: hidden; }
    footer { visibility: hidden; }

    /* Metric cards -- flat, no shadows */
    [data-testid="stMetric"] {
        background: #f8f9fa;
        border: 1px solid #e9ecef;
        border-radius: 6px;
        padding: 12px 16px;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.8rem;
        color: #6c757d;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.6rem;
        font-weight: 600;
    }

    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background: #f8f9fa;
    }
    [data-testid="stSidebar"] .block-container {
        padding-top: 1rem;
    }

    /* Section headers */
    .section-header {
        font-size: 0.75rem;
        font-weight: 600;
        color: #6c757d;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-bottom: 0.5rem;
        padding-bottom: 4px;
        border-bottom: 1px solid #dee2e6;
    }

    /* Kill switch button */
    .kill-btn button {
        background-color: #dc3545 !important;
        color: white !important;
        border: none !important;
        font-weight: 600 !important;
    }
    .kill-btn-off button {
        background-color: #f8f9fa !important;
        color: #495057 !important;
        border: 1px solid #dee2e6 !important;
    }

    /* Trade table */
    .dataframe { font-size: 0.85rem; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------
CONFIG_PATH = Path("config/settings.yaml")
KILL_SWITCH_PATH = Path("KILL_SWITCH")


def load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}


def save_config(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)


def is_kill_switch_on() -> bool:
    return KILL_SWITCH_PATH.exists()


def toggle_kill_switch() -> bool:
    if KILL_SWITCH_PATH.exists():
        KILL_SWITCH_PATH.unlink()
        return False
    else:
        KILL_SWITCH_PATH.touch()
        return True


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------
def get_account_info() -> dict | None:
    """Try to connect to Alpaca and get account info."""
    try:
        from optionharvest.api.client import AlpacaClient
        client = AlpacaClient()
        return client.get_account()
    except Exception:
        return None


def get_positions() -> list[dict]:
    """Get current option positions."""
    try:
        from optionharvest.api.client import AlpacaClient
        from optionharvest.api.orders import OrderManager
        client = AlpacaClient()
        orders = OrderManager(client)
        return orders.get_option_positions()
    except Exception:
        return []


def get_trade_history(cfg: dict) -> list[dict]:
    """Load trade history from CSV."""
    from optionharvest.analytics.tracker import TradeTracker
    tracker = TradeTracker.from_config(cfg)
    return tracker.get_all_trades()


def get_metrics(cfg: dict) -> dict:
    """Compute full performance metrics."""
    from optionharvest.analytics.tracker import TradeTracker
    from optionharvest.analytics.reporter import Reporter
    tracker = TradeTracker.from_config(cfg)
    reporter = Reporter(tracker)
    return reporter.full_metrics()


def get_weekly_rollup(cfg: dict) -> list[dict]:
    from optionharvest.analytics.tracker import TradeTracker
    from optionharvest.analytics.reporter import Reporter
    tracker = TradeTracker.from_config(cfg)
    return Reporter(tracker).weekly_rollup()


def get_monthly_rollup(cfg: dict) -> list[dict]:
    from optionharvest.analytics.tracker import TradeTracker
    from optionharvest.analytics.reporter import Reporter
    tracker = TradeTracker.from_config(cfg)
    return Reporter(tracker).monthly_rollup()


# ---------------------------------------------------------------------------
# Sidebar -- Settings Control Panel (Task 8.3)
# ---------------------------------------------------------------------------
def render_sidebar(cfg: dict) -> dict:
    """Render sidebar controls. Returns updated config."""
    strategy = cfg.get("strategy", {})
    exit_cfg = cfg.get("exit", {})
    risk = cfg.get("risk", {})

    with st.sidebar:
        st.title("OptionHarvest")

        # ---- Kill switch ----
        st.markdown('<p class="section-header">Bot Control</p>', unsafe_allow_html=True)

        kill_on = is_kill_switch_on()
        if kill_on:
            st.error("KILL SWITCH IS ON -- bot will not trade")
            css_class = "kill-btn"
            label = "Turn Off Kill Switch"
        else:
            css_class = "kill-btn-off"
            label = "Activate Kill Switch"

        with st.container():
            st.markdown(f'<div class="{css_class}">', unsafe_allow_html=True)
            if st.button(label, use_container_width=True):
                toggle_kill_switch()
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

        st.divider()

        # ---- Strategy ----
        st.markdown('<p class="section-header">Strategy</p>', unsafe_allow_html=True)

        option_type = st.selectbox(
            "Option type",
            ["put", "call", "both"],
            index=["put", "call", "both"].index(strategy.get("option_type", "put")),
        )

        target_premium = st.slider(
            "Target premium ($)",
            min_value=0.50, max_value=5.00,
            value=float(strategy.get("target_premium", 1.50)),
            step=0.25, format="$%.2f",
        )

        num_contracts = st.number_input(
            "Contracts",
            min_value=1, max_value=10,
            value=int(strategy.get("num_contracts", 1)),
        )

        strike_mode = st.selectbox(
            "Strike selection",
            ["premium", "delta"],
            index=["premium", "delta"].index(strategy.get("strike_selection", "premium")),
        )

        target_delta = st.slider(
            "Target delta",
            min_value=0.05, max_value=0.30,
            value=float(strategy.get("target_delta", 0.10)),
            step=0.01, format="%.2f",
            disabled=(strike_mode == "premium"),
        )

        st.divider()

        # ---- Exit rules ----
        st.markdown('<p class="section-header">Exit Rules</p>', unsafe_allow_html=True)

        use_stop_loss = st.toggle(
            "Stop loss",
            value=exit_cfg.get("use_stop_loss", True),
        )

        stop_loss_mult = st.slider(
            "Stop loss multiplier",
            min_value=1.5, max_value=5.0,
            value=float(exit_cfg.get("stop_loss_multiplier", 2.0)),
            step=0.5, format="%.1fx",
            disabled=(not use_stop_loss),
        )

        use_profit_target = st.toggle(
            "Profit target",
            value=exit_cfg.get("use_profit_target", True),
        )

        profit_target = st.slider(
            "Profit target %",
            min_value=25, max_value=80,
            value=int(exit_cfg.get("profit_target_pct", 0.50) * 100),
            step=5, format="%d%%",
            disabled=(not use_profit_target),
        )

        st.divider()

        # ---- Risk ----
        st.markdown('<p class="section-header">Risk Limits</p>', unsafe_allow_html=True)

        max_daily = st.number_input(
            "Max daily loss ($)",
            min_value=100, max_value=5000,
            value=int(risk.get("max_daily_loss", 500)),
            step=100,
        )

        max_weekly = st.number_input(
            "Max weekly loss ($)",
            min_value=500, max_value=10000,
            value=int(risk.get("max_weekly_loss", 1500)),
            step=250,
        )

        max_pos_pct = st.slider(
            "Max position size",
            min_value=1, max_value=20,
            value=int(risk.get("max_position_pct", 0.05) * 100),
            step=1, format="%d%%",
        )

        cb_loss = st.slider(
            "Circuit breaker (loss %)",
            min_value=1, max_value=10,
            value=int(risk.get("circuit_breaker_loss_pct", 0.03) * 100),
            step=1, format="%d%%",
        )

        cb_qqq = st.slider(
            "Circuit breaker (QQQ move %)",
            min_value=1, max_value=10,
            value=int(risk.get("circuit_breaker_qqq_move", 0.03) * 100),
            step=1, format="%d%%",
        )

        st.divider()

        # ---- Save button ----
        if st.button("Save Settings", use_container_width=True, type="primary"):
            updated = _build_config(
                cfg, option_type, target_premium, num_contracts,
                strike_mode, target_delta, use_stop_loss, stop_loss_mult,
                use_profit_target, profit_target, max_daily, max_weekly,
                max_pos_pct, cb_loss, cb_qqq,
            )
            save_config(updated)
            st.success("Saved -- takes effect on next trade")
            return updated

    return cfg


def _build_config(
    cfg, option_type, target_premium, num_contracts,
    strike_mode, target_delta, use_stop_loss, stop_loss_mult,
    use_profit_target, profit_target, max_daily, max_weekly,
    max_pos_pct, cb_loss, cb_qqq,
) -> dict:
    """Build updated config dict from sidebar values."""
    updated = dict(cfg)

    updated["strategy"] = {
        **cfg.get("strategy", {}),
        "option_type": option_type,
        "target_premium": target_premium,
        "num_contracts": num_contracts,
        "strike_selection": strike_mode,
        "target_delta": target_delta,
    }

    updated["exit"] = {
        **cfg.get("exit", {}),
        "use_stop_loss": use_stop_loss,
        "stop_loss_multiplier": stop_loss_mult,
        "use_profit_target": use_profit_target,
        "profit_target_pct": profit_target / 100,
    }

    updated["risk"] = {
        **cfg.get("risk", {}),
        "max_daily_loss": float(max_daily),
        "max_weekly_loss": float(max_weekly),
        "max_position_pct": max_pos_pct / 100,
        "circuit_breaker_loss_pct": cb_loss / 100,
        "circuit_breaker_qqq_move": cb_qqq / 100,
    }

    return updated


# ---------------------------------------------------------------------------
# Main area -- Status + Account + Positions (Task 8.1)
# ---------------------------------------------------------------------------
def render_status_bar():
    """Top bar: time, market status, kill switch status."""
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("America/New_York"))

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"**{now.strftime('%I:%M %p ET')}** -- {now.strftime('%A, %B %d')}")
    with col2:
        acct = get_account_info()
        if acct and acct.get("status") == "ACTIVE":
            st.markdown("**Alpaca:** Connected")
        else:
            st.markdown("**Alpaca:** Disconnected")
    with col3:
        if is_kill_switch_on():
            st.markdown("**Bot:** Stopped (kill switch)")
        else:
            st.markdown("**Bot:** Ready")


def render_account(cfg: dict):
    """Account metrics -- big numbers."""
    acct = get_account_info()

    if acct is None:
        st.warning("Could not connect to Alpaca -- check your .env file")
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Equity", f"${acct['equity']:,.2f}")
    with col2:
        st.metric("Cash", f"${acct['cash']:,.2f}")
    with col3:
        st.metric("Buying Power", f"${acct['buying_power']:,.2f}")


def render_positions():
    """Show current open positions."""
    positions = get_positions()

    if not positions:
        st.caption("No open positions")
        return

    st.markdown('<p class="section-header">Open Positions</p>', unsafe_allow_html=True)
    for pos in positions:
        pnl = pos.get("unrealized_pl", 0)
        color = "#28a745" if pnl >= 0 else "#dc3545"
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.text(pos["symbol"])
        with col2:
            st.text(f"Qty: {pos['qty']}")
        with col3:
            st.text(f"Entry: ${pos['avg_entry_price']:.2f}")
        with col4:
            st.markdown(f"<span style='color:{color};font-weight:600'>P&L: ${pnl:.2f}</span>",
                        unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Performance section (Task 8.2)
# ---------------------------------------------------------------------------
def render_performance(cfg: dict):
    """Performance stats and equity curve."""
    metrics = get_metrics(cfg)

    if metrics["total_trades"] == 0:
        st.caption("No trades recorded yet -- stats will appear after the first trade")
        return

    # Stats row
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        pnl = metrics["total_pnl"]
        st.metric("Total P&L", f"${pnl:,.2f}", delta=None)
    with col2:
        st.metric("Win Rate", f"{metrics['win_rate']:.1f}%")
    with col3:
        st.metric("Profit Factor", f"{metrics['profit_factor']:.2f}")
    with col4:
        st.metric("Avg Win", f"${metrics['avg_win']:.2f}")
    with col5:
        st.metric("Avg Loss", f"${metrics['avg_loss']:.2f}")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Best Trade", f"${metrics['best_trade']:.2f}")
    with col2:
        st.metric("Worst Trade", f"${metrics['worst_trade']:.2f}")
    with col3:
        st.metric("Max Drawdown", f"${metrics['max_drawdown']:.2f}")
    with col4:
        st.metric("Trading Days", str(metrics["trading_days"]))

    # Equity curve
    trades = get_trade_history(cfg)
    if len(trades) >= 2:
        render_equity_curve(trades)


def render_equity_curve(trades: list[dict]):
    """Simple cumulative P&L line chart."""
    import plotly.graph_objects as go

    dates = [t["date"] for t in trades]
    cumulative = []
    running = 0.0
    for t in trades:
        running += t["pnl"]
        cumulative.append(round(running, 2))

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=cumulative,
        mode="lines+markers",
        line={"color": "#495057", "width": 2},
        marker={"size": 5},
        hovertemplate="Date: %{x}<br>Cumulative P&L: $%{y:,.2f}<extra></extra>",
    ))

    # Color the area under the curve
    fig.add_trace(go.Scatter(
        x=dates, y=[0] * len(dates),
        mode="lines",
        line={"width": 0},
        showlegend=False,
        hoverinfo="skip",
    ))

    fig.update_layout(
        title=None,
        xaxis_title=None,
        yaxis_title="Cumulative P&L ($)",
        showlegend=False,
        margin={"l": 40, "r": 20, "t": 10, "b": 30},
        height=280,
        plot_bgcolor="white",
        xaxis={"showgrid": False},
        yaxis={"showgrid": True, "gridcolor": "#f0f0f0", "zeroline": True, "zerolinecolor": "#dee2e6"},
    )

    st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Trade history (Task 8.1 bottom area)
# ---------------------------------------------------------------------------
def render_trade_history(cfg: dict):
    """Recent trades table."""
    trades = get_trade_history(cfg)

    if not trades:
        st.caption("No trade history yet")
        return

    import pandas as pd

    # Show last 20 trades, newest first
    recent = list(reversed(trades[-20:]))
    df = pd.DataFrame(recent)

    # Format for display
    display_cols = ["date", "option_type", "strike", "entry_price", "exit_price", "pnl", "exit_reason"]
    available = [c for c in display_cols if c in df.columns]
    df = df[available]

    # Rename for readability
    rename = {
        "date": "Date",
        "option_type": "Type",
        "strike": "Strike",
        "entry_price": "Entry",
        "exit_price": "Exit",
        "pnl": "P&L",
        "exit_reason": "Reason",
    }
    df = df.rename(columns=rename)

    # Style P&L column
    def color_pnl(val):
        if isinstance(val, (int, float)):
            color = "#28a745" if val >= 0 else "#dc3545"
            return f"color: {color}; font-weight: 600"
        return ""

    styled = df.style.applymap(color_pnl, subset=["P&L"] if "P&L" in df.columns else [])
    styled = styled.format({"Strike": "${:.0f}", "Entry": "${:.2f}", "Exit": "${:.2f}", "P&L": "${:.2f}"}, na_rep="-")

    st.dataframe(styled, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Roll-ups (Task 8.2 collapsible)
# ---------------------------------------------------------------------------
def render_rollups(cfg: dict):
    """Weekly and monthly summaries."""
    col1, col2 = st.columns(2)

    with col1:
        with st.expander("Weekly breakdown"):
            weeks = get_weekly_rollup(cfg)
            if not weeks:
                st.caption("No data")
            else:
                import pandas as pd
                df = pd.DataFrame(weeks)
                df = df.rename(columns={
                    "week_start": "Week", "trades": "Trades",
                    "pnl": "P&L", "wins": "W", "losses": "L", "win_rate": "Win %",
                })
                st.dataframe(df, use_container_width=True, hide_index=True)

    with col2:
        with st.expander("Monthly breakdown"):
            months = get_monthly_rollup(cfg)
            if not months:
                st.caption("No data")
            else:
                import pandas as pd
                df = pd.DataFrame(months)
                df = df.rename(columns={
                    "month": "Month", "trades": "Trades",
                    "pnl": "P&L", "wins": "W", "losses": "L", "win_rate": "Win %",
                })
                st.dataframe(df, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    cfg = load_config()

    # Sidebar -- settings control panel
    cfg = render_sidebar(cfg)

    # Status bar
    render_status_bar()

    st.divider()

    # Account
    render_account(cfg)

    # Open positions
    render_positions()

    st.divider()

    # Performance stats
    st.subheader("Performance")
    render_performance(cfg)

    st.divider()

    # Trade history
    st.subheader("Trade History")
    render_trade_history(cfg)

    # Weekly / monthly roll-ups
    render_rollups(cfg)


if __name__ == "__main__":
    main()
else:
    # When Streamlit runs this file directly
    main()
