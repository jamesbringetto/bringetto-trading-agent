#!/usr/bin/env python3
"""Database initialization script."""

from loguru import logger

from agent.database import init_db
from agent.monitoring.logger import setup_logging


def main():
    """Initialize the database."""
    setup_logging()
    logger.info("Initializing database...")

    try:
        init_db()
        logger.info("Database initialized successfully!")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


if __name__ == "__main__":
    main()
