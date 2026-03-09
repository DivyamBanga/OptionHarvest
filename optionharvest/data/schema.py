"""
Standard DataFrame schema for 0DTE options chain data.

Every component in the pipeline reads and writes DataFrames using these
column names and types. Keeping one source of truth here prevents
mismatches between the chain generator, store, loader, validator, and
backtester.
"""

# -- Column name constants ---------------------------------------------------

DATE = "date"
STRIKE = "strike"
OPTION_TYPE = "option_type"  # "call" or "put"

# Option OHLC (open = modeled entry price, close = exact intrinsic at expiry)
OPEN = "open"
HIGH = "high"
LOW = "low"
CLOSE = "close"

VOLUME = "volume"

# Bid/ask at open (for slippage modeling)
BID_OPEN = "bid_open"
ASK_OPEN = "ask_open"

# Greeks at open
DELTA = "delta"
IMPLIED_VOL = "implied_vol"

# Underlying OHLC for the day
UNDERLYING_OPEN = "underlying_open"
UNDERLYING_HIGH = "underlying_high"
UNDERLYING_LOW = "underlying_low"
UNDERLYING_CLOSE = "underlying_close"

# -- Ordered list of all columns ---------------------------------------------

CHAIN_COLUMNS = [
    DATE,
    STRIKE,
    OPTION_TYPE,
    OPEN,
    HIGH,
    LOW,
    CLOSE,
    VOLUME,
    BID_OPEN,
    ASK_OPEN,
    DELTA,
    IMPLIED_VOL,
    UNDERLYING_OPEN,
    UNDERLYING_HIGH,
    UNDERLYING_LOW,
    UNDERLYING_CLOSE,
]

# -- Expected dtypes (for validation) ----------------------------------------

CHAIN_DTYPES = {
    DATE: "object",          # datetime.date stored as object in pandas
    STRIKE: "float64",
    OPTION_TYPE: "object",   # "call" / "put"
    OPEN: "float64",
    HIGH: "float64",
    LOW: "float64",
    CLOSE: "float64",
    VOLUME: "int64",
    BID_OPEN: "float64",
    ASK_OPEN: "float64",
    DELTA: "float64",
    IMPLIED_VOL: "float64",
    UNDERLYING_OPEN: "float64",
    UNDERLYING_HIGH: "float64",
    UNDERLYING_LOW: "float64",
    UNDERLYING_CLOSE: "float64",
}

VALID_OPTION_TYPES = {"call", "put"}
