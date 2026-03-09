# OptionHarvest — Product Requirements Document

## What Is This? (Plain English)

You sell QQQ options that expire **today** (0DTE) right when the market opens. You collect cash (premium) upfront. If QQQ doesn't move too much, the option expires worthless and you keep all the cash. If QQQ moves big against you, you lose money. The bot does this automatically every trading day on IBKR.

**Think of it like this:** You're selling lottery tickets. Most days, nobody wins and you keep the money. But occasionally someone hits, and you pay out big. The question is: do you collect enough on the quiet days to survive the blowup days? That's what the backtester answers first, and then the live bot executes.

---

## System Components (Two Major Pieces)

### Piece 1: Backtester (Build First)
Test the strategy on historical data before risking real money.

### Piece 2: Live Trading Bot (Build Second)
Execute the proven strategy automatically on IBKR.

---

## PHASE 1: BACKTESTER

### Task 1: Data Pipeline
**Goal:** Get historical 0DTE QQQ options data into your system.

- [ ] **1.1** Choose a data provider and set up API access
  - Options: Polygon.io (affordable, good API), ThetaData (popular for 0DTE), CBOE DataShop (gold standard, expensive)
  - Recommendation: Start with Polygon.io ($29/mo developer tier)
- [ ] **1.2** Write a data fetcher that pulls QQQ options chains for a given date
  - Input: date (e.g., 2025-01-15)
  - Output: all QQQ options expiring that day, with open/high/low/close prices, bid/ask, volume, open interest
- [ ] **1.3** Store fetched data locally (SQLite or Parquet files) so you don't re-fetch
  - Schema: date, strike, option_type (put/call), open, high, low, close, bid, ask, volume, underlying_open, underlying_close
- [ ] **1.4** Build a data loader that reads from local storage
  - Should return a clean DataFrame for any requested date
- [ ] **1.5** Validate data quality
  - Check for missing dates, missing strikes, zero-volume options, stale quotes
  - Log warnings for suspicious data points

### Task 2: Strategy Engine
**Goal:** Simulate the sell-at-open, expire-at-close logic.

- [ ] **2.1** Define strategy parameters as a config
  ```
  target_premium: 1.50        # desired premium per contract ($150 actual)
  option_type: "put"           # "put", "call", or "both" (strangle)
  strike_selection: "premium"  # "premium" (match target $), "delta" (match target delta)
  num_contracts: 1             # how many contracts to sell
  use_spread: false            # if true, buy a protective wing (credit spread)
  spread_width: 5              # distance of protective wing in $ (if use_spread=true)
  ```
- [ ] **2.2** Build strike selector
  - Given the options chain at open, find the strike whose mid-price is closest to `target_premium`
  - If `option_type` is "both", find one put and one call
  - If `use_spread` is true, also buy the wing (put at strike - spread_width, or call at strike + spread_width)
- [ ] **2.3** Build entry logic
  - At market open, record: strike chosen, entry premium (mid-price), underlying price, timestamp
  - Apply slippage model: assume fill at mid-price minus a configurable slippage (e.g., $0.05)
- [ ] **2.4** Build exit logic
  - Default: hold to expiry (4:00 PM ET). P&L = premium collected - max(0, intrinsic value at close)
  - Optional stop-loss: if option price hits X times entry premium, close early (buy back)
  - Optional profit target: if option decays to Y% of entry, close early (lock in gains)
- [ ] **2.5** Build P&L calculator
  - For short naked option: P&L = entry_premium - settlement_price (per contract, multiply by 100)
  - For credit spread: P&L = net_credit - max(0, spread_intrinsic_at_close)
  - Account for commissions: IBKR charges ~$0.65/contract

### Task 3: Position & Risk Tracking
**Goal:** Track margin, buying power, and risk per trade.

- [ ] **3.1** Define account parameters
  ```
  starting_capital: 25000      # initial account balance
  margin_model: "reg_t"        # "reg_t" or "portfolio_margin"
  max_daily_risk: 0.05         # max 5% of account at risk per day
  ```
- [ ] **3.2** Calculate margin requirement per trade
  - Naked put margin ≈ max(20% of underlying - OTM amount, 10% of underlying) × 100
  - Credit spread margin = spread_width × 100
  - Reject trades that exceed available margin or max_daily_risk
- [ ] **3.3** Track daily account balance
  - Starting balance + cumulative P&L through each day
  - If balance drops below maintenance margin, flag it

### Task 4: Analytics & Reporting
**Goal:** Answer "is this strategy worth trading live?"

- [ ] **4.1** Calculate core metrics
  - Total P&L, average daily P&L
  - Win rate (% of days profitable)
  - Average win size vs. average loss size
  - Profit factor (gross wins / gross losses)
  - Max drawdown (peak-to-trough decline)
  - Sharpe ratio (annualized risk-adjusted return)
  - Worst single day loss
  - Longest losing streak
- [ ] **4.2** Generate equity curve
  - Plot cumulative P&L over time
  - Overlay QQQ price for context
- [ ] **4.3** Generate trade log
  - CSV/table with every trade: date, strike, type, entry premium, exit price, P&L, QQQ move
- [ ] **4.4** Stress test analysis
  - Isolate performance on high-vol days (VIX > 25)
  - Isolate performance on big QQQ move days (> 2%)
  - Show how different premium targets change results
- [ ] **4.5** Parameter sensitivity report
  - Run the backtest across a grid of premium targets (e.g., $0.50 to $3.00 in $0.25 steps)
  - Show which premium target has the best risk-adjusted return

---

## PHASE 2: LIVE TRADING BOT

### Task 5: IBKR Connection
**Goal:** Establish reliable connection to IBKR's API.

- [ ] **5.1** Set up ib_insync connection manager
  - Connect to TWS/IB Gateway (port 7497 for paper, 7496 for live)
  - Handle disconnects and auto-reconnect
  - Log all connection events
- [ ] **5.2** Verify account access
  - Pull account summary (buying power, net liquidation value)
  - Confirm options trading permissions for QQQ
- [ ] **5.3** Set up paper trading environment
  - All development and testing happens on paper account FIRST
  - Never touch live account until backtester proves the strategy works

### Task 6: Market Data & Chain Fetching
**Goal:** Get live QQQ options data from IBKR.

- [ ] **6.1** Subscribe to QQQ real-time quotes
  - Get current price, bid, ask at market open
- [ ] **6.2** Fetch today's 0DTE options chain
  - Request all strikes expiring today
  - Get bid/ask/last/volume for each strike
- [ ] **6.3** Filter and rank strikes
  - Apply same strike selection logic from backtester (Task 2.2)
  - Use live bid/ask (not mid) for realistic pricing

### Task 7: Order Execution
**Goal:** Place sell orders at market open, manage through the day.

- [ ] **7.1** Build order placer
  - At 9:31 AM ET (1 min after open to let spreads settle), place sell order
  - Use limit order at the mid-price (or slightly below mid for faster fill)
  - Set time-in-force to DAY
- [ ] **7.2** Build fill monitor
  - Wait for fill confirmation
  - If not filled within 2 minutes, adjust price (widen by $0.05 increments)
  - Log fill price, timestamp, slippage vs. expected
- [ ] **7.3** Build position monitor
  - Track open position throughout the day
  - Calculate real-time P&L
  - Check stop-loss / profit target conditions
- [ ] **7.4** Build exit handler
  - If stop-loss triggered: place buy-to-close market order immediately
  - If profit target hit: place buy-to-close limit order
  - If neither: let option expire at 4:00 PM ET (auto-exercise/expire handled by IBKR)
  - For ITM options at expiry: IBKR auto-exercises — ensure you handle assignment risk (close before 3:50 PM if close to the money)
- [ ] **7.5** End-of-day cleanup
  - Verify all positions are closed/expired
  - Log final P&L for the day
  - Send notification (email/Telegram/Discord) with daily summary

### Task 8: Scheduling & Automation
**Goal:** Bot runs automatically every trading day.

- [ ] **8.1** Build trading calendar
  - Know which days are trading days (exclude weekends, market holidays)
  - Handle early close days (day before Thanksgiving, etc.)
- [ ] **8.2** Build scheduler
  - Start bot at 9:25 AM ET (5 min before open)
  - Execute strategy at 9:31 AM ET
  - Monitor until 4:00 PM ET
  - Shutdown after end-of-day cleanup
- [ ] **8.3** Handle edge cases
  - Market halts (circuit breakers)
  - TWS/Gateway crashes mid-day
  - Internet disconnection
  - Option chain not available (holiday week, special events)

### Task 9: Safety & Risk Controls
**Goal:** Don't blow up the account.

- [ ] **9.1** Pre-trade checks
  - Verify sufficient margin before placing trade
  - Verify daily loss limit hasn't been hit
  - Verify the strategy parameters are within sane bounds
  - Confirm it's a valid trading day and time
- [ ] **9.2** Intraday circuit breakers
  - If unrealized loss exceeds X% of account, close all positions
  - If QQQ moves more than Y% from open, close all positions
  - Manual kill switch (ability to stop the bot instantly)
- [ ] **9.3** Daily loss limit
  - If realized loss today exceeds max_daily_risk, do not trade
  - If cumulative weekly loss exceeds a threshold, pause for the week
- [ ] **9.4** Logging & audit trail
  - Log every decision, order, fill, and error
  - Store logs with timestamps for review
  - Daily P&L log in a persistent database

---

## PHASE 3: MONITORING & ITERATION

### Task 10: Dashboard & Alerts
**Goal:** Know what's happening without watching the screen.

- [ ] **10.1** Build a simple web dashboard (Streamlit or Flask)
  - Show today's trade: strike, premium, current P&L
  - Show cumulative performance (equity curve)
  - Show account balance and margin usage
- [ ] **10.2** Set up alerts
  - Trade placed notification
  - Stop-loss triggered notification
  - Daily P&L summary notification
  - Error/disconnection alert
- [ ] **10.3** Compare live results vs. backtest
  - Track slippage (expected fill vs. actual fill)
  - Track strategy drift (are live results matching backtest expectations?)

---

## Tech Stack

| Component          | Technology                        |
|--------------------|-----------------------------------|
| Language           | Python 3.11+                      |
| IBKR API           | ib_insync                         |
| Data (backtest)    | Polygon.io API                    |
| Data storage       | SQLite + Parquet files            |
| Data processing    | pandas, numpy                     |
| Visualization      | plotly, matplotlib                |
| Dashboard          | Streamlit                         |
| Scheduling         | APScheduler or system cron        |
| Notifications      | Telegram Bot API or Discord       |
| Logging            | Python logging + rotating files   |
| Config             | YAML config files                 |

---

## Project Structure

```
OptionHarvest/
├── config/
│   ├── strategy.yaml          # strategy parameters
│   ├── ibkr.yaml              # IBKR connection settings
│   └── alerts.yaml            # notification settings
├── data/
│   ├── raw/                   # raw API responses
│   ├── processed/             # cleaned parquet files
│   └── optionharvest.db       # SQLite database
├── src/
│   ├── data/
│   │   ├── fetcher.py         # pull data from Polygon/ThetaData
│   │   ├── store.py           # save/load local data
│   │   └── validator.py       # data quality checks
│   ├── backtest/
│   │   ├── engine.py          # main backtest loop
│   │   ├── strategy.py        # strike selection, entry/exit logic
│   │   ├── portfolio.py       # position tracking, margin calc
│   │   └── analytics.py       # metrics, reporting, plots
│   ├── live/
│   │   ├── connector.py       # IBKR connection manager
│   │   ├── market_data.py     # live quotes and chains
│   │   ├── executor.py        # order placement and management
│   │   ├── monitor.py         # position monitoring, stop-losses
│   │   └── scheduler.py       # daily scheduling
│   ├── risk/
│   │   ├── margin.py          # margin calculations
│   │   ├── limits.py          # daily/weekly loss limits
│   │   └── circuit_breaker.py # emergency exit logic
│   ├── dashboard/
│   │   └── app.py             # Streamlit dashboard
│   └── utils/
│       ├── calendar.py        # trading calendar
│       ├── notifications.py   # Telegram/Discord alerts
│       └── logger.py          # logging setup
├── tests/
│   ├── test_strategy.py
│   ├── test_margin.py
│   ├── test_backtest.py
│   └── test_executor.py
├── notebooks/
│   └── exploration.ipynb      # data exploration, quick analysis
├── PRD.md                     # this file
├── README.md
├── requirements.txt
└── pyproject.toml
```

---

## Build Order (What to Do First)

1. **Data pipeline** (Task 1) — nothing works without data
2. **Strategy engine** (Task 2) — core logic
3. **Analytics** (Task 4) — see if the strategy is even worth trading
4. **Risk tracking** (Task 3) — understand margin requirements
5. **IBKR connection** (Task 5) — bridge to live trading
6. **Market data** (Task 6) — live chain fetching
7. **Order execution** (Task 7) — actually place trades
8. **Safety controls** (Task 9) — protect the account
9. **Scheduling** (Task 8) — automate daily runs
10. **Dashboard & alerts** (Task 10) — monitor without babysitting

---

## Key Risks to Remember

| Risk | What Happens | Mitigation |
|------|-------------|------------|
| Tail risk | QQQ drops 4% in a day, single trade wipes a month of gains | Stop-losses, position sizing, credit spreads instead of naked |
| Slippage | Real fills are worse than backtested mid-prices | Model bid-ask spread, use conservative fill assumptions |
| Data quality | Bad historical data gives false confidence | Validate data, cross-reference multiple sources |
| API failure | IBKR disconnects mid-trade | Auto-reconnect, manual kill switch, position monitoring |
| Over-optimization | Strategy works in backtest but not live (curve fitting) | Out-of-sample testing, walk-forward analysis |
| Margin call | Account doesn't have enough margin for assigned options | Pre-trade margin checks, close ITM options before expiry |
