#!/usr/bin/env python3
"""
Database initialization script for Railway deployment.

Run this script to:
1. Run all Alembic migrations
2. Seed initial strategy data

Usage:
    python scripts/init_db.py
"""

import os
import sys

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alembic import command
from alembic.config import Config
from loguru import logger


def run_migrations():
    """Run Alembic migrations."""
    logger.info("Running database migrations...")

    # Get the alembic.ini path
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    alembic_ini = os.path.join(project_root, "alembic.ini")

    if not os.path.exists(alembic_ini):
        logger.error(f"alembic.ini not found at {alembic_ini}")
        return False

    # Create Alembic config
    alembic_cfg = Config(alembic_ini)

    # Override the SQLAlchemy URL from environment
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL environment variable not set")
        return False

    # Handle Railway's postgres:// vs postgresql:// URL format
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    alembic_cfg.set_main_option("sqlalchemy.url", database_url)

    try:
        # Run migrations
        command.upgrade(alembic_cfg, "head")
        logger.info("Migrations completed successfully!")
        return True
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False


def seed_strategies():
    """Seed initial strategy data."""
    logger.info("Seeding initial strategies...")

    from agent.config.constants import StrategyType
    from agent.database import get_session
    from agent.database.models import Strategy

    strategies = [
        {
            "name": "Opening Range Breakout",
            "type": StrategyType.ORB.value,
            "parameters": {
                "range_minutes": 30,
                "breakout_threshold": 0.002,
                "stop_loss_pct": 1.0,
                "take_profit_pct": 2.0,
                "position_size_pct": 10.0,
                "symbols": ["SPY", "QQQ", "IWM"],
            },
            "version": "1.0.0",
            "is_active": True,
        },
        {
            "name": "VWAP Mean Reversion",
            "type": StrategyType.VWAP_REVERSION.value,
            "parameters": {
                "deviation_threshold": 2.0,
                "stop_loss_pct": 0.5,
                "take_profit_pct": 1.0,
                "position_size_pct": 8.0,
                "symbols": ["AAPL", "MSFT", "GOOGL", "NVDA", "TSLA"],
            },
            "version": "1.0.0",
            "is_active": True,
        },
        {
            "name": "Momentum Scalp",
            "type": StrategyType.MOMENTUM_SCALP.value,
            "parameters": {
                "momentum_threshold": 0.01,
                "volume_multiplier": 2.0,
                "stop_loss_pct": 0.3,
                "take_profit_pct": 0.5,
                "position_size_pct": 5.0,
                "max_positions": 5,
            },
            "version": "1.0.0",
            "is_active": True,
        },
        {
            "name": "Gap and Go",
            "type": StrategyType.GAP_AND_GO.value,
            "parameters": {
                "min_gap_pct": 3.0,
                "volume_threshold": 1000000,
                "stop_loss_pct": 1.5,
                "take_profit_pct": 3.0,
                "position_size_pct": 15.0,
                "max_positions": 2,
            },
            "version": "1.0.0",
            "is_active": True,
        },
        {
            "name": "EOD Reversal",
            "type": StrategyType.EOD_REVERSAL.value,
            "parameters": {
                "reversal_threshold": 0.015,
                "entry_time": "15:00",
                "stop_loss_pct": 0.5,
                "take_profit_pct": 1.0,
                "position_size_pct": 10.0,
                "symbols": ["SPY", "QQQ"],
            },
            "version": "1.0.0",
            "is_active": True,
        },
    ]

    try:
        with get_session() as session:
            for strat_data in strategies:
                # Check if strategy already exists
                existing = session.query(Strategy).filter(
                    Strategy.name == strat_data["name"]
                ).first()

                if existing:
                    logger.info(f"Strategy '{strat_data['name']}' already exists, skipping")
                    continue

                strategy = Strategy(
                    name=strat_data["name"],
                    type=strat_data["type"],
                    parameters=strat_data["parameters"],
                    version=strat_data["version"],
                    is_active=strat_data["is_active"],
                )
                session.add(strategy)
                logger.info(f"Added strategy: {strat_data['name']}")

            session.commit()

        logger.info("Strategy seeding completed!")
        return True
    except Exception as e:
        logger.error(f"Strategy seeding failed: {e}")
        return False


def main():
    """Main entry point."""
    logger.info("=" * 50)
    logger.info("Database Initialization Script")
    logger.info("=" * 50)

    # Run migrations
    if not run_migrations():
        logger.error("Failed to run migrations. Exiting.")
        sys.exit(1)

    # Seed strategies
    if not seed_strategies():
        logger.warning("Failed to seed strategies, but migrations succeeded.")

    logger.info("=" * 50)
    logger.info("Database initialization complete!")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
