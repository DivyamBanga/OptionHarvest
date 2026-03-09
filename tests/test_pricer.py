"""Tests for Black-Scholes pricing and IV estimation."""

import math

import pytest

from optionharvest.data.pricer import (
    apply_skew,
    bs_delta,
    bs_price,
    estimate_iv,
    norm_cdf,
    norm_pdf,
)


# ---------------------------------------------------------------------------
# norm_cdf / norm_pdf
# ---------------------------------------------------------------------------

class TestNormFunctions:
    def test_cdf_at_zero(self):
        assert abs(norm_cdf(0) - 0.5) < 1e-10

    def test_cdf_symmetry(self):
        assert abs(norm_cdf(1.0) + norm_cdf(-1.0) - 1.0) < 1e-10

    def test_cdf_extremes(self):
        assert norm_cdf(10.0) > 0.9999
        assert norm_cdf(-10.0) < 0.0001

    def test_pdf_at_zero(self):
        expected = 1.0 / math.sqrt(2 * math.pi)
        assert abs(norm_pdf(0) - expected) < 1e-10

    def test_pdf_symmetry(self):
        assert abs(norm_pdf(1.5) - norm_pdf(-1.5)) < 1e-10


# ---------------------------------------------------------------------------
# bs_price
# ---------------------------------------------------------------------------

class TestBSPrice:
    """Test Black-Scholes option pricing."""

    def test_atm_call_has_positive_value(self):
        price = bs_price(500, 500, 1 / 252, 0.05, 0.20, "call")
        assert price > 0

    def test_atm_put_has_positive_value(self):
        price = bs_price(500, 500, 1 / 252, 0.05, 0.20, "put")
        assert price > 0

    def test_expired_call_itm(self):
        # spot=505, strike=500 → intrinsic = 5
        assert bs_price(505, 500, 0, 0.05, 0.20, "call") == 5.0

    def test_expired_call_otm(self):
        # spot=495, strike=500 → worthless
        assert bs_price(495, 500, 0, 0.05, 0.20, "call") == 0.0

    def test_expired_put_itm(self):
        # spot=495, strike=500 → intrinsic = 5
        assert bs_price(495, 500, 0, 0.05, 0.20, "put") == 5.0

    def test_expired_put_otm(self):
        assert bs_price(505, 500, 0, 0.05, 0.20, "put") == 0.0

    def test_put_call_parity(self):
        """C - P = S - K*exp(-rT) for same strike/expiry."""
        S, K, T, r, vol = 500, 500, 1 / 252, 0.05, 0.20
        call = bs_price(S, K, T, r, vol, "call")
        put = bs_price(S, K, T, r, vol, "put")
        expected = S - K * math.exp(-r * T)
        assert abs((call - put) - expected) < 0.01

    def test_deep_otm_call_near_zero(self):
        # strike way above spot, 0DTE → nearly worthless
        price = bs_price(500, 550, 1 / 252, 0.05, 0.20, "call")
        assert price < 0.01

    def test_deep_otm_put_near_zero(self):
        price = bs_price(500, 450, 1 / 252, 0.05, 0.20, "put")
        assert price < 0.01

    def test_higher_vol_means_higher_price(self):
        low_vol = bs_price(500, 500, 1 / 252, 0.05, 0.15, "call")
        high_vol = bs_price(500, 500, 1 / 252, 0.05, 0.30, "call")
        assert high_vol > low_vol

    def test_price_is_non_negative(self):
        """Price should never be negative for any reasonable inputs."""
        for spot in [400, 500, 600]:
            for strike in [450, 500, 550]:
                for vol in [0.05, 0.20, 0.80]:
                    for opt in ["call", "put"]:
                        p = bs_price(spot, strike, 1 / 252, 0.05, vol, opt)
                        assert p >= 0, f"Negative price: {spot=} {strike=} {vol=} {opt=}"


# ---------------------------------------------------------------------------
# bs_delta
# ---------------------------------------------------------------------------

class TestBSDelta:
    def test_atm_call_delta_near_half(self):
        d = bs_delta(500, 500, 1 / 252, 0.05, 0.20, "call")
        assert 0.45 < d < 0.60

    def test_atm_put_delta_near_neg_half(self):
        d = bs_delta(500, 500, 1 / 252, 0.05, 0.20, "put")
        assert -0.60 < d < -0.45

    def test_deep_itm_call_delta_near_one(self):
        d = bs_delta(550, 500, 1 / 252, 0.05, 0.20, "call")
        assert d > 0.95

    def test_deep_otm_put_delta_near_zero(self):
        d = bs_delta(550, 500, 1 / 252, 0.05, 0.20, "put")
        assert d > -0.05

    def test_expired_call_itm(self):
        assert bs_delta(505, 500, 0, 0.05, 0.20, "call") == 1.0

    def test_expired_call_otm(self):
        assert bs_delta(495, 500, 0, 0.05, 0.20, "call") == 0.0

    def test_expired_put_itm(self):
        assert bs_delta(495, 500, 0, 0.05, 0.20, "put") == -1.0

    def test_call_delta_range(self):
        """Call delta must be in [0, 1]."""
        for strike in range(480, 520):
            d = bs_delta(500, strike, 1 / 252, 0.05, 0.20, "call")
            assert 0 <= d <= 1

    def test_put_delta_range(self):
        """Put delta must be in [-1, 0]."""
        for strike in range(480, 520):
            d = bs_delta(500, strike, 1 / 252, 0.05, 0.20, "put")
            assert -1 <= d <= 0


# ---------------------------------------------------------------------------
# estimate_iv
# ---------------------------------------------------------------------------

class TestEstimateIV:
    def test_typical_vix(self):
        iv = estimate_iv(20.0)
        # VIX 20 → 0.20 * 1.15 * 0.90 = 0.207
        assert abs(iv - 0.207) < 0.001

    def test_low_vix(self):
        iv = estimate_iv(10.0)
        assert iv > 0.05  # above floor

    def test_extreme_vix(self):
        iv = estimate_iv(80.0)
        assert iv <= 2.0  # capped

    def test_very_low_vix_floor(self):
        iv = estimate_iv(1.0)
        assert iv >= 0.05

    def test_custom_ratios(self):
        iv = estimate_iv(20.0, qqq_vix_ratio=1.0, term_structure_adj=1.0)
        assert abs(iv - 0.20) < 0.001


# ---------------------------------------------------------------------------
# apply_skew
# ---------------------------------------------------------------------------

class TestApplySkew:
    def test_atm_no_skew(self):
        """ATM options should use base IV."""
        assert apply_skew(0.20, 500, 500, "call") == 0.20
        assert apply_skew(0.20, 500, 500, "put") == 0.20

    def test_otm_put_higher_iv(self):
        """OTM puts should have higher IV (crash fear)."""
        iv = apply_skew(0.20, 490, 500, "put")
        assert iv > 0.20

    def test_otm_call_higher_iv(self):
        """OTM calls should have slightly higher IV."""
        iv = apply_skew(0.20, 510, 500, "call")
        assert iv > 0.20

    def test_put_skew_steeper_than_call(self):
        """Put skew should be steeper than call skew at same distance."""
        put_iv = apply_skew(0.20, 490, 500, "put")
        call_iv = apply_skew(0.20, 510, 500, "call")
        assert put_iv > call_iv

    def test_itm_uses_base_iv(self):
        """ITM options should use base IV (no skew adjustment)."""
        assert apply_skew(0.20, 510, 500, "put") == 0.20   # ITM put
        assert apply_skew(0.20, 490, 500, "call") == 0.20  # ITM call

    def test_skew_increases_with_distance(self):
        """Further OTM = higher IV."""
        iv_near = apply_skew(0.20, 495, 500, "put")
        iv_far = apply_skew(0.20, 480, 500, "put")
        assert iv_far > iv_near
