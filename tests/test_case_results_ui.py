"""
Tests for the Case Results section on the Overview page.
Verifies dynamic calculation display, case validation checks label,
and absence of hard-coded overrides in calculation engines.
"""
import inspect
import pandas as pd
import pytest

from src.business_logic import run_analysis
from src.customer_targets import build_customer_targets
from src.data_loader import load_workbook
import src.business_logic
import src.customer_targets

SAMPLE_PATH = "sample_data/CompanyX_Data.xlsx"


def test_case_results_section_present_in_app():
    """Verify that Case Results section and small label exist in app.py."""
    with open("app.py", "r", encoding="utf-8") as f:
        content = f.read()

    assert "Case Results" in content
    assert "Case validation checks" in content
    assert "Classification Benchmarks" in content
    assert "Required SKU Checks" in content
    assert "For SKU1005: First Three Target Customers" in content


def test_calculation_engine_has_no_hardcoded_overrides():
    """Verify that calculation engines do NOT hardcode case results or override actual math."""
    logic_src = inspect.getsource(src.business_logic)
    target_src = inspect.getsource(src.customer_targets)

    # Calculation functions must not hard-code expected output numbers as return overrides
    assert "163841" not in logic_src
    assert "163841" not in target_src
    assert "SKU1005" not in logic_src
    assert "Customer 220" not in target_src


def test_dynamic_case_results_match_case_benchmarks():
    """Verify that dynamic analysis results match the expected case validation checks."""
    raw = load_workbook(SAMPLE_PATH)
    res = run_analysis(*raw)
    targets = build_customer_targets(res["clean_item_master"], res["clean_sales"], res["analysis_items"], customers=raw[3])

    items = res["analysis_items"]
    counts = items["Class"].value_counts()

    # Classification counts
    assert int(counts.get("Red List", 0)) == 7
    assert int(counts.get("No Action", 0)) == 13
    assert int(counts.get("Push", 0)) == 18
    assert float(items.loc[items["Class"] == "Push", "Aged Value"].sum()) == pytest.approx(163841.0)

    # Required SKU checks
    sku_classes = items.set_index("SKU")["Class"].to_dict()
    assert sku_classes.get("SKU1001") == "No Action"
    assert sku_classes.get("SKU1006") == "Push"
    assert sku_classes.get("SKU1019") == "Push"
    assert sku_classes.get("SKU1005") == "Push"

    # SKU1005 top 3 targets
    targets_1005 = targets.get("SKU1005", pd.DataFrame())
    assert not targets_1005.empty
    top3 = targets_1005.head(3)["CustomerName"].tolist()
    assert top3 == ["Customer 220", "Customer 224", "Customer 214"]
