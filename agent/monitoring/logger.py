"""Logging configuration using loguru."""

import sys
from pathlib import Path

from loguru import logger

from agent.config.settings import get_settings


def setup_logging() -> None:
    """Configure logging for the trading agent."""
    settings = get_settings()

    # Remove default handler
    logger.remove()

    # Console logging format
    if settings.log_format == "json":
        console_format = (
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
            "{level: <8} | "
            "{name}:{function}:{line} | "
            "{message}"
        )
    else:
        console_format = (
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        )

    # Add console handler
    logger.add(
        sys.stderr,
        format=console_format,
        level=settings.log_level,
        colorize=settings.log_format != "json",
    )

    # Add file handler for errors
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    logger.add(
        log_dir / "error.log",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
        level="ERROR",
        rotation="10 MB",
        retention="30 days",
        compression="gz",
    )

    # Add file handler for trades
    logger.add(
        log_dir / "trades.log",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {message}",
        level="INFO",
        rotation="50 MB",
        retention="90 days",
        filter=lambda record: "trade" in record["message"].lower(),
    )

    # Add file handler for all logs
    logger.add(
        log_dir / "agent.log",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
        level=settings.log_level,
        rotation="50 MB",
        retention="7 days",
        compression="gz",
    )

    logger.info(f"Logging configured - level: {settings.log_level}, format: {settings.log_format}")


def get_logger(name: str):
    """Get a logger with a specific name."""
    return logger.bind(name=name)
