"""
OptionHarvest Dashboard

Run: streamlit run optionharvest/dashboard/app.py
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import streamlit as st
import yaml

# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------
st.set_page_config(page_title="OptionHarvest", layout="wide")

st.markdown("""
<style>
    .block-container { padding-top: 1.2rem; padding-bottom: 0; }
    #MainMenu, header, footer { visibility: hidden; }
    [data-testid="stMetricValue"] { font-size: 1.5rem; font-weight: 600; }
    [data-testid="stMetricLabel"] { font-size: 0.75rem; color: #888; text-transform: uppercase; letter-spacing: 0.5px; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Config + kill switch
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
    KILL_SWITCH_PATH.touch()
    return True


# ---------------------------------------------------------------------------
# Data (cached to avoid redundant API calls)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=10)
def get_account_info() -> dict | None:
    try:
        from optionharvest.api.client import AlpacaClient
        return AlpacaClient().get_account()
    except Exception:
        return None


@st.cache_data(ttl=10)
def get_positions() -> list[dict]:
    try:
        from optionharvest.api.client import AlpacaClient
        from optionharvest.api.orders import OrderManager
        return OrderManager(AlpacaClient()).get_option_positions()
    except Exception:
        return []


def get_trade_history(cfg: dict) -> list[dict]:
    from optionharvest.analytics.tracker import TradeTracker
    return TradeTracker.from_config(cfg).get_all_trades()


def get_metrics(cfg: dict) -> dict:
    from optionharvest.analytics.tracker import TradeTracker
    from optionharvest.analytics.reporter import Reporter
    return Reporter(TradeTracker.from_config(cfg)).full_metrics()


def get_weekly_rollup(cfg: dict) -> list[dict]:
    from optionharvest.analytics.tracker import TradeTracker
    from optionharvest.analytics.reporter import Reporter
    return Reporter(TradeTracker.from_config(cfg)).weekly_rollup()


def get_monthly_rollup(cfg: dict) -> list[dict]:
    from optionharvest.analytics.tracker import TradeTracker
    from optionharvest.analytics.reporter import Reporter
    return Reporter(TradeTracker.from_config(cfg)).monthly_rollup()


# ---------------------------------------------------------------------------
# Build updated config from sidebar values
# ---------------------------------------------------------------------------
def _build_config(
    cfg, option_type, target_premium, num_contracts,
    strike_mode, target_delta, use_stop_loss, stop_loss_mult,
    use_profit_target, profit_target, max_daily, max_weekly,
    max_pos_pct, cb_loss, cb_qqq,
) -> dict:
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
# Sidebar
# ---------------------------------------------------------------------------
def render_sidebar(cfg: dict) -> dict:
    strategy = cfg.get("strategy", {})
    exit_cfg = cfg.get("exit", {})
    risk = cfg.get("risk", {})

    with st.sidebar:
        # ---- Kill switch ----
        kill_on = is_kill_switch_on()
        if kill_on:
            st.error("Kill switch is ON")
            if st.button("Turn Off", use_container_width=True):
                toggle_kill_switch()
                st.rerun()
        else:
            if st.button("Kill Switch", use_container_width=True, type="secondary"):
                toggle_kill_switch()
                st.rerun()

        st.markdown("---")

        # ---- What to sell ----
        st.caption("STRATEGY")

        option_type = st.selectbox(
            "Type",
            ["put", "call", "both"],
            index=["put", "call", "both"].index(strategy.get("option_type", "put")),
        )

        col1, col2 = st.columns(2)
        with col1:
            target_premium = st.number_input(
                "Premium ($)",
                min_value=0.25, max_value=10.0,
                value=float(strategy.get("target_premium", 1.50)),
                step=0.25, format="%.2f",
            )
        with col2:
            num_contracts = st.number_input(
                "Qty",
                min_value=1, max_value=10,
                value=int(strategy.get("num_contracts", 1)),
            )

        st.markdown("---")

        # ---- When to exit ----
        st.caption("EXIT RULES")

        use_stop_loss = st.toggle("Stop loss", value=exit_cfg.get("use_stop_loss", True))
        stop_loss_mult = st.slider(
            "Stop loss at", 1.5, 5.0,
            value=float(exit_cfg.get("stop_loss_multiplier", 2.0)),
            step=0.5, format="%.1fx entry",
            disabled=(not use_stop_loss),
        )

        use_profit_target = st.toggle("Profit target", value=exit_cfg.get("use_profit_target", True))
        profit_target = st.slider(
            "Take profit at", 25, 80,
            value=int(exit_cfg.get("profit_target_pct", 0.50) * 100),
            step=5, format="%d%% decay",
            disabled=(not use_profit_target),
        )

        st.markdown("---")

        # ---- Advanced (rarely changed) ----
        with st.expander("Advanced"):
            st.caption("STRIKE SELECTION")
            strike_mode = st.selectbox(
                "Mode", ["premium", "delta"],
                index=["premium", "delta"].index(strategy.get("strike_selection", "premium")),
            )
            target_delta = st.slider(
                "Target delta", 0.05, 0.30,
                value=float(strategy.get("target_delta", 0.10)),
                step=0.01, format="%.2f",
                disabled=(strike_mode == "premium"),
            )

            st.caption("RISK LIMITS")
            max_daily = st.number_input(
                "Max daily loss ($)", 100, 5000,
                value=int(risk.get("max_daily_loss", 500)), step=100,
            )
            max_weekly = st.number_input(
                "Max weekly loss ($)", 500, 10000,
                value=int(risk.get("max_weekly_loss", 1500)), step=250,
            )
            max_pos_pct = st.slider(
                "Max position size", 1, 20,
                value=int(risk.get("max_position_pct", 0.05) * 100),
                format="%d%%",
            )
            cb_loss = st.slider(
                "Circuit breaker (loss)", 1, 10,
                value=int(risk.get("circuit_breaker_loss_pct", 0.03) * 100),
                format="%d%%",
            )
            cb_qqq = st.slider(
                "Circuit breaker (QQQ move)", 1, 10,
                value=int(risk.get("circuit_breaker_qqq_move", 0.03) * 100),
                format="%d%%",
            )

        # ---- Save ----
        if st.button("Save Settings", use_container_width=True, type="primary"):
            updated = _build_config(
                cfg, option_type, target_premium, num_contracts,
                strike_mode, target_delta, use_stop_loss, stop_loss_mult,
                use_profit_target, profit_target, max_daily, max_weekly,
                max_pos_pct, cb_loss, cb_qqq,
            )
            save_config(updated)
            st.success("Saved")
            return updated

    return cfg


# ---------------------------------------------------------------------------
# Main content
# ---------------------------------------------------------------------------
def main():
    cfg = load_config()
    cfg = render_sidebar(cfg)

    # ---- Header ----
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("America/New_York"))
    acct = get_account_info()
    connected = acct is not None and acct.get("status") == "ACTIVE"

    left, right = st.columns([3, 1])
    with left:
        st.markdown(f"### OptionHarvest")
    with right:
        status = "Connected" if connected else "Disconnected"
        st.caption(f"{now.strftime('%I:%M %p ET  //  %a %b %d')}  //  {status}")

    if not connected:
        st.warning("Could not connect to Alpaca")
        return

    # ---- Account + Position (the two things you came to see) ----
    positions = get_positions()

    if positions:
        # Active position -- show it prominently
        pos = positions[0]
        pnl = pos.get("unrealized_pl", 0)
        pnl_color = "green" if pnl >= 0 else "red"

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Equity", f"${acct['equity']:,.0f}")
        with col2:
            st.metric("Position", pos["symbol"][-15:])
        with col3:
            st.metric("Entry", f"${pos['avg_entry_price']:.2f}")
        with col4:
            st.metric("Unrealized P&L", f"${pnl:,.2f}",
                       delta=f"{'+'if pnl>=0 else ''}{pnl:.2f}")
    else:
        col1, col2 = st.columns([1, 2])
        with col1:
            st.metric("Equity", f"${acct['equity']:,.0f}")
        with col2:
            st.caption("No open position right now")

    # ---- Performance ----
    metrics = get_metrics(cfg)
    trades = get_trade_history(cfg)

    if metrics["total_trades"] > 0:
        st.markdown("---")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total P&L", f"${metrics['total_pnl']:,.2f}")
        with col2:
            st.metric("Win Rate", f"{metrics['win_rate']:.0f}%")
        with col3:
            st.metric("Trades", str(metrics["total_trades"]))

        # Equity curve
        if len(trades) >= 2:
            _render_equity_curve(trades)

        # More stats (collapsed)
        with st.expander("More stats"):
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("Avg Win", f"${metrics['avg_win']:.2f}")
            with c2:
                st.metric("Avg Loss", f"${metrics['avg_loss']:.2f}")
            with c3:
                st.metric("Max Drawdown", f"${metrics['max_drawdown']:.2f}")
            with c4:
                pf = metrics['profit_factor']
                st.metric("Profit Factor", f"{pf:.2f}" if pf < 100 else "---")

            _render_rollups(cfg)

    # ---- Trade log ----
    if trades:
        st.markdown("---")
        st.caption("RECENT TRADES")
        _render_trade_table(trades)
    else:
        st.markdown("---")
        st.caption("No trades yet -- stats and history will appear after the first trade.")


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------
def _render_equity_curve(trades: list[dict]):
    import plotly.graph_objects as go

    dates = [t["date"] for t in trades]
    cumulative = []
    total = 0.0
    for t in trades:
        total += t["pnl"]
        cumulative.append(round(total, 2))

    # Color segments green/red based on whether cumulative is positive/negative
    colors = ["#22863a" if c >= 0 else "#cb2431" for c in cumulative]

    fig = go.Figure(go.Scatter(
        x=dates, y=cumulative,
        mode="lines",
        line={"color": "#333", "width": 2},
        fill="tozeroy",
        fillcolor="rgba(0,0,0,0.03)",
        hovertemplate="%{x}<br>$%{y:,.2f}<extra></extra>",
    ))

    fig.update_layout(
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        height=200,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis={"showgrid": False, "showticklabels": True, "tickfont": {"size": 10, "color": "#aaa"}},
        yaxis={"showgrid": False, "showticklabels": True, "tickfont": {"size": 10, "color": "#aaa"},
               "zeroline": True, "zerolinecolor": "#ddd", "zerolinewidth": 1},
        showlegend=False,
    )

    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def _render_trade_table(trades: list[dict]):
    import pandas as pd

    recent = list(reversed(trades[-10:]))
    df = pd.DataFrame(recent)

    cols = ["date", "option_type", "strike", "entry_price", "exit_price", "pnl", "exit_reason"]
    df = df[[c for c in cols if c in df.columns]]
    df = df.rename(columns={
        "date": "Date", "option_type": "Type", "strike": "Strike",
        "entry_price": "Entry", "exit_price": "Exit", "pnl": "P&L", "exit_reason": "Exit",
    })

    st.dataframe(
        df.style
        .format({"Strike": "${:.0f}", "Entry": "${:.2f}", "Exit (price)": "${:.2f}", "P&L": "${:+.2f}"}, na_rep="-")
        .applymap(
            lambda v: f"color: {'#22863a' if v >= 0 else '#cb2431'}; font-weight: 600"
            if isinstance(v, (int, float)) else "",
            subset=["P&L"] if "P&L" in df.columns else [],
        ),
        use_container_width=True,
        hide_index=True,
    )


def _render_rollups(cfg: dict):
    import pandas as pd

    weeks = get_weekly_rollup(cfg)
    months = get_monthly_rollup(cfg)

    if weeks:
        st.caption("WEEKLY")
        df = pd.DataFrame(weeks)[["week_start", "trades", "pnl", "win_rate"]]
        df.columns = ["Week", "Trades", "P&L", "Win %"]
        st.dataframe(df, use_container_width=True, hide_index=True)

    if months:
        st.caption("MONTHLY")
        df = pd.DataFrame(months)[["month", "trades", "pnl", "win_rate"]]
        df.columns = ["Month", "Trades", "P&L", "Win %"]
        st.dataframe(df, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
else:
    main()
