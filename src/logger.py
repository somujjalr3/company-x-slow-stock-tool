"""
Centralized logging module for Company X Slow Stock Action Tool.

Provides standardized, thread-safe, structured logging across all business logic,
data ingestion, validation, customer targeting, and export pipelines.
"""
import logging
import os
import sys
from typing import Optional

# Standard logger namespace
DEFAULT_LOGGER_NAME = "CompanyX.SlowStock"
LOG_FORMAT = "%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Returns a configured standard logger instance.
    
    If name is provided, returns a child logger under 'CompanyX.SlowStock.<name>'.
    Otherwise returns the root application logger.
    """
    logger_name = f"{DEFAULT_LOGGER_NAME}.{name}" if name else DEFAULT_LOGGER_NAME
    logger = logging.getLogger(logger_name)

    # Avoid duplicate handlers if already configured
    if not logger.handlers and not logging.getLogger(DEFAULT_LOGGER_NAME).handlers:
        level_name = os.environ.get("SLOWSTOCK_LOG_LEVEL", "INFO").upper()
        level = getattr(logging, level_name, logging.INFO)
        logger.setLevel(level)

        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.propagate = False
    elif not logger.handlers:
        # Inherit root logger configuration
        logger.propagate = True

    return logger
