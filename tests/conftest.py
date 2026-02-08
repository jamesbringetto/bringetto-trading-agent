"""Pytest configuration and fixtures."""

import os
from decimal import Decimal

import pytest

# Set test environment defaults (real env vars take precedence)
os.environ.setdefault("ENVIRONMENT", "paper")
os.environ.setdefault("ALPACA_API_KEY", "test_placeholder_key")
os.environ.setdefault("ALPACA_SECRET_KEY", "test_placeholder_secret")
os.environ.setdefault("DATABASE_URL", "postgresql://localhost:5432/test_db")
os.environ.setdefault("API_SECRET_KEY", "test_api_secret_not_for_production")


@pytest.fixture
def sample_account_value():
    """Sample account value for testing."""
    return Decimal("100000.00")


@pytest.fixture
def sample_buying_power():
    """Sample buying power for testing."""
    return Decimal("50000.00")
