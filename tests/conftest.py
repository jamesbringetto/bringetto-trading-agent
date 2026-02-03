"""Pytest configuration and fixtures."""

import os
from decimal import Decimal

import pytest

# Set test environment
os.environ["ENVIRONMENT"] = "paper"
os.environ["ALPACA_API_KEY"] = "test_key"
os.environ["ALPACA_SECRET_KEY"] = "test_secret"
os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5432/test_db"


@pytest.fixture
def sample_account_value():
    """Sample account value for testing."""
    return Decimal("100000.00")


@pytest.fixture
def sample_buying_power():
    """Sample buying power for testing."""
    return Decimal("50000.00")
