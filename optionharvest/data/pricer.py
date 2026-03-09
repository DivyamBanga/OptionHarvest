"""
Black-Scholes option pricing and IV estimation for synthetic 0DTE chains.

Uses real VIX data as an implied-volatility proxy, applies a skew model
for OTM options, then prices each strike with the standard BS formula.

Key design choice:  the *close* price (expiry) is always the exact
intrinsic value — only the *open* price is modeled.  This makes exit
P&L calculations exact and limits model error to the entry side.
"""

from __future__ import annotations

import math


# ---------------------------------------------------------------------------
# Normal distribution helpers (no scipy dependency)
# ---------------------------------------------------------------------------

def norm_cdf(x: float) -> float:
    """Cumulative distribution function of the standard normal."""
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0


def norm_pdf(x: float) -> float:
    """Probability density function of the standard normal."""
    return math.exp(-x * x / 2.0) / math.sqrt(2.0 * math.pi)


# ---------------------------------------------------------------------------
# Black-Scholes pricing
# ---------------------------------------------------------------------------

def bs_price(
    spot: float,
    strike: float,
    time_years: float,
    rate: float,
    vol: float,
    option_type: str,
) -> float:
    """
    European option price via Black-Scholes.

    Parameters
    ----------
    spot : underlying price
    strike : strike price
    time_years : time to expiry in years  (0 → intrinsic value)
    rate : annualised risk-free rate (e.g. 0.05 for 5 %)
    vol : annualised implied volatility (e.g. 0.20 for 20 %)
    option_type : "call" or "put"

    Returns
    -------
    Theoretical option price (≥ 0).
    """
    if time_years <= 0:
        # At expiry the option is worth its intrinsic value.
        if option_type == "call":
            return max(0.0, spot - strike)
        return max(0.0, strike - spot)

    sqrt_t = math.sqrt(time_years)
    d1 = (math.log(spot / strike) + (rate + vol * vol / 2.0) * time_years) / (
        vol * sqrt_t
    )
    d2 = d1 - vol * sqrt_t

    if option_type == "call":
        price = spot * norm_cdf(d1) - strike * math.exp(-rate * time_years) * norm_cdf(d2)
    else:
        price = (
            strike * math.exp(-rate * time_years) * norm_cdf(-d2)
            - spot * norm_cdf(-d1)
        )

    return max(0.0, price)


def bs_delta(
    spot: float,
    strike: float,
    time_years: float,
    rate: float,
    vol: float,
    option_type: str,
) -> float:
    """
    Option delta (∂price/∂spot).

    Returns a value in [-1, 1].
    """
    if time_years <= 0:
        if option_type == "call":
            return 1.0 if spot > strike else (0.5 if spot == strike else 0.0)
        return -1.0 if spot < strike else (-0.5 if spot == strike else 0.0)

    sqrt_t = math.sqrt(time_years)
    d1 = (math.log(spot / strike) + (rate + vol * vol / 2.0) * time_years) / (
        vol * sqrt_t
    )

    if option_type == "call":
        return norm_cdf(d1)
    return norm_cdf(d1) - 1.0


# ---------------------------------------------------------------------------
# Implied-volatility estimation from VIX
# ---------------------------------------------------------------------------

def estimate_iv(
    vix_close: float,
    *,
    qqq_vix_ratio: float = 1.15,
    term_structure_adj: float = 0.90,
    iv_floor: float = 0.05,
    iv_cap: float = 2.00,
) -> float:
    """
    Estimate 0DTE QQQ ATM implied volatility from the VIX close.

    1. VIX (30-day SPX IV) is converted to a decimal  (VIX 20 → 0.20).
    2. Scaled up for QQQ vs SPX  (QQQ is ~15 % more volatile on average).
    3. Adjusted down for the 0DTE term-structure effect (shorter-dated
       options tend to have slightly lower IV in normal markets).
    4. Clamped to [iv_floor, iv_cap].
    """
    base_iv = vix_close / 100.0
    scaled = base_iv * qqq_vix_ratio * term_structure_adj
    return max(iv_floor, min(scaled, iv_cap))


# ---------------------------------------------------------------------------
# Volatility skew model
# ---------------------------------------------------------------------------

def apply_skew(
    atm_iv: float,
    strike: float,
    spot: float,
    option_type: str,
    *,
    put_skew_slope: float = 1.5,
    call_skew_slope: float = 0.3,
) -> float:
    """
    Adjust ATM IV for the volatility skew.

    OTM puts carry a higher IV (crash-fear premium).
    OTM calls carry a slightly higher IV (right-tail risk).
    ATM and ITM options use the base ATM IV.

    The slope controls how steeply IV rises with distance from ATM
    (expressed as a fraction of spot).
    """
    distance_pct = abs(strike - spot) / spot

    if option_type == "put" and strike < spot:      # OTM put
        return atm_iv * (1.0 + put_skew_slope * distance_pct)
    if option_type == "call" and strike > spot:     # OTM call
        return atm_iv * (1.0 + call_skew_slope * distance_pct)

    return atm_iv  # ATM or ITM — use base IV
