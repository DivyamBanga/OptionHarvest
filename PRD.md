# OptionHarvest -- Product Requirements Document

## What Is This? (Plain English)

A bot that sells QQQ options expiring **today** (0DTE) at market open, collects cash (premium), and lets them expire by end of day. It runs on **Alpaca's free paper trading** account so you test the strategy with fake money using real market prices.

**Think of it like this:** You're selling insurance policies that expire tonight. Most days nothing bad happens and you keep the money. Some days a storm hits and you pay out. This bot does it automatically every trading day, tracks everything, and tells you how it went.

**Why paper trading instead of backtesting?** Real market data, real order fills, real bid-ask spreads. No simulated prices, no modeling errors. You see exactly how the strategy performs in live conditions without risking a dollar.

---

## Why Alpaca?

- **Free** -- no subscription, no commissions on options
- **Paper trading built in** -- $100K fake account, real market prices
- **0DTE supported** -- daily expirations, all option types
- **Python SDK** -- `alpaca-py` library, clean API
- **No desktop app needed** -- pure API, no TWS/Gateway to run
- **Simple auth** -- just an API key and secret

---

## System Overview (One Piece, Three Layers)

```
STRATEGY LAYER       -- what to sell, when to enter/exit
    |
EXECUTION LAYER      -- place orders, monitor fills, manage positions
    |
SAFETY LAYER         -- stop-losses, daily limits, kill switch
```

All three run together as one bot, every trading day.

---

## PHASE 1: CORE TRADING BOT

### Task 1: Alpaca Connection
**Goal:** Connect to Alpaca and verify everything works.

- [ ] **1.1** Set up Alpaca paper trading account
  - Sign up at alpaca.markets (free, email only)
  - Generate API key + secret for paper trading
  - Store credentials in `.env` file (never commit this)
- [ ] **1.2** Build Alpaca client wrapper
  - Initialize `TradingClient` with `paper=True`
  - Initialize `OptionHistoricalDataClient` for quotes
  - Initialize `StockHistoricalDataClient` for QQQ price
  - Handle connection errors and retries
- [ ] **1.3** Verify account access
  - Pull account info (buying power, equity, cash)
  - Confirm options trading is enabled (Level 1+ needed)
  - Log account status at startup

### Task 2: Market Data
**Goal:** Get live QQQ price and today's 0DTE options chain from Alpaca.

- [ ] **2.1** Fetch QQQ current price
  - Use `StockLatestTradeRequest` to get real-time price
  - This is the "spot" price for strike selection
- [ ] **2.2** Fetch today's 0DTE options chain
  - Use `GetOptionContractsRequest` with:
    - `underlying_symbols=["QQQ"]`
    - `expiration_date=today`
    - `status="active"`
    - `strike_price_gte` and `strike_price_lte` (spot +/- 10%)
  - Returns all active QQQ options expiring today
- [ ] **2.3** Get live quotes for each option
  - Use `OptionLatestQuoteRequest` to get bid/ask for each strike
  - Calculate mid-price: `(bid + ask) / 2`
  - Filter out illiquid options (open interest < 100, wide spreads)
- [ ] **2.4** Build chain DataFrame
  - Standardize into: strike, type, bid, ask, mid, open_interest, delta
  - Calculate delta using Black-Scholes (reuse pricer.py from existing code)
  - This DataFrame feeds into the strategy engine

### Task 3: Strategy Engine
**Goal:** Decide what to sell based on the live chain.

- [ ] **3.1** Define strategy parameters as config
  ```yaml
  target_premium: 1.50        # desired premium per contract ($150 actual)
  option_type: "put"           # "put", "call", or "both" (strangle)
  strike_selection: "premium"  # "premium" (match target $) or "delta" (match target delta)
  target_delta: 0.10           # used if strike_selection is "delta"
  num_contracts: 1             # how many contracts to sell
  use_spread: false            # if true, buy a protective wing (credit spread)
  spread_width: 5              # distance of wing in $ (if use_spread=true)
  ```
- [ ] **3.2** Build strike selector
  - Scan the chain for the option whose mid-price is closest to `target_premium`
  - If using delta selection, find the option closest to `target_delta`
  - If `option_type` is "both", find one put and one call (strangle)
  - If `use_spread` is true, also pick the protective wing strike
  - Return the selected contract symbol(s) and expected premium
- [ ] **3.3** Build entry signal
  - Check: is it a trading day? Is it after 9:31 AM ET?
  - Check: do we already have an open position? (don't double up)
  - Check: does the selected option meet minimum liquidity?
  - If all checks pass, signal "ENTER"
- [ ] **3.4** Build exit signal
  - **Default:** hold to expiry (Alpaca auto-closes at 3:30 PM ET for 0DTE)
  - **Stop-loss:** if option price hits X times entry premium, signal "EXIT"
  - **Profit target:** if option decays to Y% of entry, signal "EXIT"
  - **Time-based:** close by 3:15 PM ET to avoid Alpaca's auto-liquidation

### Task 4: Order Execution
**Goal:** Place sell orders and manage fills.

- [ ] **4.1** Build order placer
  - At 9:31 AM ET, place sell-to-open limit order at the mid-price
  - Contract symbol format: `QQQ260309P00500000` (OCC standard)
  - Time-in-force: `day`
  - For spreads: use multi-leg order with `OrderClass.MLEG`
- [ ] **4.2** Build fill monitor
  - Poll order status every 5 seconds
  - If not filled within 2 minutes, adjust price (move $0.05 toward market)
  - After 3 adjustments, switch to market order or cancel
  - Log: fill price, time, slippage vs. expected
- [ ] **4.3** Build position monitor
  - After fill, track position throughout the day
  - Poll latest quote every 60 seconds (configurable)
  - Calculate unrealized P&L: `(entry_premium - current_mid) * 100 * num_contracts`
  - Check exit signals on every poll
- [ ] **4.4** Build exit handler
  - Stop-loss triggered: place buy-to-close market order immediately
  - Profit target hit: place buy-to-close limit order
  - Time exit (3:15 PM): place buy-to-close market order
  - For spreads: close both legs
- [ ] **4.5** End-of-day cleanup
  - Verify all positions are closed or expired
  - If any position remains open, force close it
  - Record final P&L for the day
  - Log full trade details

### Task 5: Risk Controls
**Goal:** Don't blow up the (paper) account.

- [ ] **5.1** Pre-trade checks
  - Verify sufficient buying power before placing trade
  - Verify daily loss limit hasn't been hit
  - Verify strategy parameters are within sane bounds
  - Confirm it's a valid trading day and within market hours
- [ ] **5.2** Intraday circuit breakers
  - If unrealized loss exceeds X% of account, close all positions
  - If QQQ moves more than Y% from open, close all positions
  - Manual kill switch: a flag file that stops the bot instantly
- [ ] **5.3** Daily loss limit
  - If realized loss today exceeds `max_daily_risk`, skip trading
  - If cumulative weekly loss exceeds a threshold, pause for the week
- [ ] **5.4** Logging and audit trail
  - Log every decision, order, fill, and error with timestamps
  - Save trade log to CSV: date, strike, type, entry, exit, P&L, QQQ move
  - Daily summary written to `data/trades/` directory

---

## PHASE 2: AUTOMATION AND TRACKING

### Task 6: Scheduling
**Goal:** Bot runs automatically every trading day.

- [ ] **6.1** Build trading calendar
  - Know which days are trading days (exclude weekends, holidays)
  - Handle early close days (day before Thanksgiving, etc.)
- [ ] **6.2** Build scheduler
  - Start bot at 9:25 AM ET (5 min before open)
  - Execute strategy at 9:31 AM ET
  - Monitor positions until 3:15 PM ET
  - Run end-of-day cleanup
  - Shutdown after cleanup
- [ ] **6.3** Handle edge cases
  - Market halts (circuit breakers)
  - API errors or timeouts
  - Internet disconnection
  - No 0DTE options available (holiday week)

### Task 7: Analytics and Reporting
**Goal:** Track performance over time.

- [ ] **7.1** Calculate core metrics
  - Total P&L, average daily P&L
  - Win rate (% of days profitable)
  - Average win size vs. average loss size
  - Profit factor (gross wins / gross losses)
  - Max drawdown (peak-to-trough decline)
  - Worst single day loss
  - Longest losing streak
- [ ] **7.2** Generate trade log
  - CSV with every trade: date, strike, type, entry, exit, P&L, QQQ move
  - Append daily, never overwrite
- [ ] **7.3** Daily summary report
  - Print to console after each trading day
  - Include: today's P&L, cumulative P&L, win rate, account balance
- [ ] **7.4** Weekly/monthly roll-up
  - Aggregate daily results into weekly and monthly summaries
  - Identify best/worst weeks, trends over time

---

## PHASE 3: DASHBOARD AND CONTROL PANEL

### Task 8: Dashboard
**Goal:** One page to see everything and control the bot. Clean, minimal, no clutter.

**Design principles:**
- **Minimal** -- only show what matters, no decorative junk
- **2-3 colors max** -- neutral background, green for profit, red for loss. That's it.
- **Big numbers** -- P&L and account balance should be the first thing you see
- **Grouped logically** -- status up top, controls in sidebar, history below
- **Looks like a tool, not a template** -- no gradients, no card shadows, no icons everywhere. Flat, clean, tight spacing. The kind of thing a trader builds for themselves.

- [ ] **8.1** Dashboard layout (Streamlit)
  - **Top bar:** bot status (running/stopped/waiting), current time ET, market open/closed
  - **Main area:**
    - Account: equity, cash, buying power -- big readable numbers
    - Today's trade: symbol, strike, entry price, current price, unrealized P&L
    - If no trade today: "No trade today" with the reason why
  - **Bottom area:**
    - Trade history table (last 20 trades from CSV)
    - Equity curve chart (cumulative P&L over time)
  - **Sidebar:** settings control panel (see 8.3)

- [ ] **8.2** Performance stats section
  - Total P&L, win rate, profit factor -- shown as simple numbers, not charts
  - Average win vs average loss
  - Best day, worst day, current streak
  - Weekly and monthly roll-up (collapsible)
  - Equity curve: one clean line chart, no grid clutter

- [ ] **8.3** Settings control panel (sidebar)
  - **Strategy controls:**
    - Target premium (slider: $0.50 - $5.00)
    - Option type (dropdown: put / call / both)
    - Number of contracts (1-10)
    - Strike selection mode (premium / delta)
    - Target delta (slider: 0.05 - 0.30)
  - **Exit controls:**
    - Stop-loss multiplier (slider: 1.5x - 5.0x)
    - Profit target % (slider: 25% - 80%)
    - Toggle stop-loss on/off
    - Toggle profit target on/off
  - **Risk controls:**
    - Max daily loss (input: $100 - $5000)
    - Max weekly loss (input: $500 - $10000)
    - Max position size % (slider: 1% - 20%)
    - Circuit breaker loss % (slider: 1% - 10%)
    - Circuit breaker QQQ move % (slider: 1% - 10%)
  - **Bot controls:**
    - Kill switch button (big red, toggles KILL_SWITCH file)
    - "Save settings" button (writes to settings.yaml, takes effect next trade)
  - Changes save to `config/settings.yaml` -- bot picks them up on next cycle

- [ ] **8.4** Alerts
  - Trade placed notification
  - Stop-loss triggered notification
  - Daily P&L summary notification
  - Error/disconnection alert
  - (Start with console/log alerts. Telegram/Discord is optional later.)

---

## Tech Stack

| Component          | Technology                        |
|--------------------|-----------------------------------|
| Language           | Python 3.11+                      |
| Broker API         | Alpaca (`alpaca-py`)              |
| Market data        | Alpaca (real-time quotes)         |
| Greeks calculation  | Black-Scholes (built-in)         |
| Data storage       | CSV + Parquet files               |
| Data processing    | pandas, numpy                     |
| Visualization      | plotly, matplotlib                |
| Dashboard          | Streamlit (monitor + control panel)|
| Scheduling         | APScheduler                       |
| Notifications      | Telegram Bot API or Discord       |
| Logging            | Python logging + rotating files   |
| Config             | YAML config files                 |

---

## Project Structure

```
OptionHarvest/
├── config/
│   └── settings.yaml          # all configuration in one file
├── data/
│   └── trades/                # daily trade logs (CSV)
├── optionharvest/
│   ├── __init__.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── client.py          # Alpaca client wrapper
│   │   ├── market_data.py     # live quotes and chains
│   │   └── orders.py          # order placement and management
│   ├── strategy/
│   │   ├── __init__.py
│   │   ├── selector.py        # strike selection logic
│   │   └── signals.py         # entry/exit signal logic
│   ├── trading/
│   │   ├── __init__.py
│   │   ├── executor.py        # trade execution engine
│   │   ├── monitor.py         # position monitoring
│   │   └── scheduler.py       # daily scheduling
│   ├── risk/
│   │   ├── __init__.py
│   │   ├── limits.py          # daily/weekly loss limits
│   │   └── circuit_breaker.py # emergency exit logic
│   ├── analytics/
│   │   ├── __init__.py
│   │   ├── tracker.py         # P&L tracking and trade log
│   │   └── reporter.py        # daily/weekly reports
│   ├── dashboard/
│   │   └── app.py             # Streamlit dashboard + control panel
│   └── utils/
│       ├── __init__.py
│       ├── logger.py          # logging setup
│       ├── calendar.py        # trading calendar
│       └── pricer.py          # Black-Scholes (from existing code)
├── tests/
│   ├── test_selector.py
│   ├── test_signals.py
│   ├── test_limits.py
│   └── test_executor.py
├── .env.example               # API key template
├── PRD.md                     # this file
├── README.md
├── requirements.txt
└── pyproject.toml
```

---

## Build Order (What to Do First)

1. **Alpaca connection** (Task 1) -- can't do anything without it
2. **Market data** (Task 2) -- get live chains and quotes
3. **Strategy engine** (Task 3) -- decide what to sell
4. **Order execution** (Task 4) -- actually place trades
5. **Risk controls** (Task 5) -- protect the account
6. **Scheduling** (Task 6) -- automate daily runs
7. **Analytics** (Task 7) -- track how it's going
8. **Dashboard** (Task 8) -- monitor and control the bot from one page

---

## Key Alpaca Details

| Detail | Value |
|--------|-------|
| Paper trading URL | `https://paper-api.alpaca.markets` |
| Starting balance | $100,000 (fake money) |
| Options commissions | $0 (free) |
| Options levels | Level 1-3 (paper has all enabled) |
| Contract format | `QQQ260309P00500000` (OCC standard) |
| Order types | market, limit, stop, stop_limit |
| Auto-liquidation | 3:30 PM ET for expiring options |
| Python SDK | `alpaca-py` (pip install alpaca-py) |
| Rate limits | 200 requests/minute |

---

## Key Risks to Remember

| Risk | What Happens | Mitigation |
|------|-------------|------------|
| Tail risk | QQQ drops 4% in a day, single trade wipes a month of gains | Stop-losses, position sizing, credit spreads |
| Slippage | Real fills worse than mid-price | Limit orders, adjust if not filled |
| API downtime | Alpaca is unreachable, can't manage position | Circuit breaker, auto-close before 3:15 PM |
| Assignment risk | ITM option gets exercised early | Close ITM positions before 3:00 PM |
| Over-leveraging | Selling too many contracts relative to account | Pre-trade buying power check, max daily risk |
| Illiquid options | Wide bid-ask spreads, bad fills | Filter by open interest, skip illiquid strikes |

---

## Daily Trading Flow (What the Bot Does)

```
9:25 AM  -- Bot starts, connects to Alpaca
9:25 AM  -- Checks: is today a trading day? any existing positions?
9:30 AM  -- Market opens
9:31 AM  -- Fetches QQQ price and 0DTE options chain
9:31 AM  -- Selects strike based on strategy parameters
9:31 AM  -- Places sell-to-open limit order
9:31-9:35 -- Monitors for fill, adjusts price if needed
9:35 AM  -- Position is open (or skipped if no fill)
9:35 AM - 3:15 PM  -- Monitors position every 60 seconds
           -- Checks stop-loss and profit target on each poll
           -- Logs unrealized P&L
3:15 PM  -- If position still open, closes it (avoid auto-liquidation)
3:30 PM  -- Alpaca auto-closes any remaining expiring positions
4:00 PM  -- Market closes, options expire
4:01 PM  -- End-of-day cleanup: record P&L, update trade log
4:02 PM  -- Bot shuts down
```
