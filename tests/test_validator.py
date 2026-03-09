"""Tests for ChainValidator."""

from datetime import date

import pandas as pd
import pytest

from optionharvest.data import schema as S
from optionharvest.data.validator import ChainValidator


@pytest.fixture
def validator():
    return ChainValidator()


class TestChainValidator:
    def test_valid_chain_passes(self, validator, sample_chain):
        result = validator.validate(sample_chain)
        assert result.passed
        assert len(result.errors) == 0

    def test_empty_df_fails(self, validator):
        result = validator.validate(pd.DataFrame())
        assert not result.passed
        assert any("empty" in e.lower() for e in result.errors)

    def test_missing_columns_fails(self, validator):
        df = pd.DataFrame({"strike": [500], "option_type": ["call"]})
        result = validator.validate(df)
        assert not result.passed
        assert any("Missing columns" in e for e in result.errors)

    def test_invalid_option_type_fails(self, validator, sample_chain):
        bad = sample_chain.copy()
        bad.loc[0, S.OPTION_TYPE] = "strangle"
        result = validator.validate(bad)
        assert not result.passed
        assert any("option_type" in e.lower() for e in result.errors)

    def test_negative_prices_fail(self, validator, sample_chain):
        bad = sample_chain.copy()
        bad.loc[0, S.OPEN] = -1.0
        result = validator.validate(bad)
        assert not result.passed
        assert any("negative" in e.lower() for e in result.errors)

    def test_nan_prices_fail(self, validator, sample_chain):
        bad = sample_chain.copy()
        bad.loc[0, S.CLOSE] = float("nan")
        result = validator.validate(bad)
        assert not result.passed
        assert any("nan" in e.lower() for e in result.errors)

    def test_bid_above_ask_fails(self, validator, sample_chain):
        bad = sample_chain.copy()
        bad.loc[0, S.BID_OPEN] = 5.00
        bad.loc[0, S.ASK_OPEN] = 3.00
        result = validator.validate(bad)
        assert not result.passed
        assert any("Bid > Ask" in e for e in result.errors)

    def test_call_delta_warning(self, validator, sample_chain):
        bad = sample_chain.copy()
        # Set a call's delta to negative (invalid)
        call_mask = bad[S.OPTION_TYPE] == "call"
        bad.loc[call_mask, S.DELTA] = -0.5
        result = validator.validate(bad)
        assert any("delta" in w.lower() for w in result.warnings)

    def test_put_delta_warning(self, validator, sample_chain):
        bad = sample_chain.copy()
        put_mask = bad[S.OPTION_TYPE] == "put"
        bad.loc[put_mask, S.DELTA] = 0.5
        result = validator.validate(bad)
        assert any("delta" in w.lower() for w in result.warnings)

    def test_validate_range(self, validator, sample_chain):
        # Create a two-day DataFrame
        day1 = sample_chain.copy()
        day2 = sample_chain.copy()
        day2[S.DATE] = date(2024, 6, 4)

        combined = pd.concat([day1, day2], ignore_index=True)
        results = validator.validate_range(combined)

        assert len(results) == 2
        assert all(r.passed for r in results)

    def test_summary_format(self, validator, sample_chain):
        result = validator.validate(sample_chain)
        summary = result.summary()
        assert "PASS" in summary
