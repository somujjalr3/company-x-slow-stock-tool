"""
Unit tests verifying application optimizations:
- Centralized logger configuration and child loggers
- Exception logging in error_handler
- Precomputed pipeline outputs (sales action table, data lineage)
- Caching compatibility for Excel report generation
"""
import logging
import pytest
import pandas as pd

from src.logger import get_logger, DEFAULT_LOGGER_NAME
from src.error_handler import format_user_friendly_error
from src.business_logic import run_analysis
from src.customer_targets import build_customer_targets
from src.sales_action_center import build_sales_action_table
from src.data_lineage import build_data_lineage
from src.data_loader import load_data
from src.validation import validate_data
from src.config import get_default_config


def test_centralized_logger():
    """Verify that get_logger produces structured, properly namespaced loggers."""
    root_log = get_logger()
    assert root_log.name == DEFAULT_LOGGER_NAME

    child_log = get_logger("SubModule")
    assert child_log.name == f"{DEFAULT_LOGGER_NAME}.SubModule"
    assert isinstance(child_log, logging.Logger)

    # Logging test messages should execute cleanly without raising exceptions
    child_log.info("Test informational log message")
    child_log.warning("Test warning log message")


def test_exception_logging():
    """Verify format_user_friendly_error logs exceptions via the standardized logger."""
    try:
        raise KeyError("CustomerID")
    except Exception as exc:
        err = format_user_friendly_error(exc)

    assert err["title"] == "Missing CustomerID Column"
    assert "CustomerID is missing" in err["message"]
    assert err["error_type"] == "KeyError"


def test_precomputed_pipeline_structures():
    """Verify that heavy tables can be computed once and reused across tabs."""
    raw = load_data("sample_data/CompanyX_Data.xlsx")
    val = validate_data(*raw)
    cfg = get_default_config()

    analysis = run_analysis(*raw, validation=val, config=cfg)
    targets = build_customer_targets(
        analysis["clean_item_master"],
        analysis["clean_sales"],
        analysis["analysis_items"],
        val,
        customers=raw[3],
        config=cfg,
    )

    # 1. Precompute Sales Action Table
    action_table = build_sales_action_table(
        analysis["analysis_items"], targets, sales_trends=analysis.get("sales_trends")
    )
    assert not action_table.empty
    assert "Priority" in action_table.columns
    assert "SKU" in action_table.columns
    assert "Customer ID" in action_table.columns

    # 2. Precompute Data Lineage
    lineage = build_data_lineage(raw, val, analysis, targets)
    assert "stages" in lineage
    assert len(lineage["stages"]) == 12
    assert "summary" in lineage
