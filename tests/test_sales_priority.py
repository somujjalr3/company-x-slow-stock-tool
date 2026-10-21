"""
Unit Tests for Sales Priority Score Module.

Verifies:
  1. Strict R1-R7 Invariance:
       - Red List = 7, No Action = 13, Push = 18, Push Aged Value = 163,841
       - SKU1001 = No Action, SKU1006 = Push, SKU1019 = Push, SKU1005 = Push
       - Sales Priority Score never modifies or replaces Push classification.
  2. Deterministic 0-100 score calculation across all 6 operational dimensions:
       - Aged Inventory Value (0-25 pts)
       - Total Inventory Value (0-15 pts)
       - Months to Clear (0-20 pts)
       - Sales Trend (0-15 pts)
       - Sales Velocity (0-10 pts)
       - Risk Score alignment (0-15 pts)
  3. Priority Level classification:
       - Critical (80-100)
       - High (60-79)
       - Medium (30-59)
       - Low (0-29)
  4. Deterministic 'Why Priority?' explanation generation.
  5. Ranked Push SKU table construction and ordering:
       - Correct columns: Rank, SKU, Description, Category, Aged Value,
         Months to Clear, Sales Trend, Risk Score, Priority Score, Recommended Action.
       - Ordered by Priority Score descending.
       - Correct 18 Push items identified.
  6. Edge cases (infinite MTC, zero aged value, zero sales, missing values).
"""

import pytest
import numpy as np
import pandas as pd

from src.data_loader import load_workbook
from src.business_logic import run_analysis
from src.sales_priority import (
    calculate_sales_priority,
    calculate_sales_priority_row,
    get_ranked_push_table,
)


@pytest.fixture(scope="module")
def sample_analysis():
    im, st, sl, cu = load_workbook("sample_data/CompanyX_Data.xlsx")
    return run_analysis(im, st, sl, cu)


def test_01_core_rules_r1_to_r7_invariant(sample_analysis):
    """Confirm Sales Priority Score preserves all core R1-R7 benchmarks exactly."""
    items = sample_analysis["analysis_items"]

    counts = items["Class"].value_counts()
    assert counts.get("Red List", 0) == 7, "Red List count must remain 7"
    assert counts.get("No Action", 0) == 13, "No Action count must remain 13"
    assert counts.get("Push", 0) == 18, "Push count must remain 18"

    push_aged_value = float(items.loc[items["Class"] == "Push", "Aged Value"].sum())
    assert push_aged_value == 163841, f"Push Aged Value must be 163,841, got {push_aged_value}"

    sku_class = items.set_index("SKU")["Class"].to_dict()
    assert sku_class["SKU1001"] == "No Action"
    assert sku_class["SKU1006"] == "Push"
    assert sku_class["SKU1019"] == "Push"
    assert sku_class["SKU1005"] == "Push"


def test_02_priority_score_range_and_tiers():
    """Verify 0-100 score bounds and Priority Level tier assignment."""
    # Low priority item
    low_item = {
        "Aged Value": 0, "Inventory Value": 5000, "Months to Clear": 2.0,
        "Sales Trend": "Growing", "Avg Monthly Sales": 50, "Total Stock": 100,
        "Risk Score": 10
    }
    res_low = calculate_sales_priority_row(low_item)
    assert 0 <= res_low["priority_score"] <= 100
    assert res_low["priority_level"] == "Low"

    # Critical priority item (high aged value, extended MTC, declining sales, high risk)
    crit_item = {
        "Aged Value": 30000, "Inventory Value": 70000, "Months to Clear": 14.0,
        "Sales Trend": "Declining", "Avg Monthly Sales": 5, "Total Stock": 200,
        "Risk Score": 85
    }
    res_crit = calculate_sales_priority_row(crit_item)
    assert res_crit["priority_score"] >= 80
    assert res_crit["priority_level"] == "Critical"


def test_03_why_priority_explanation():
    """Verify 'Why Priority?' explanation contains aged value, months to clear, and trend."""
    item = {
        "Aged Value": 18360, "Inventory Value": 50000, "Months to Clear": 6.4,
        "Sales Trend": "Growing", "Avg Monthly Sales": 80, "Total Stock": 511,
        "Risk Score": 60
    }
    res = calculate_sales_priority_row(item)
    why = res["why_priority"]

    assert "priority because the item has" in why
    assert "₹18,360 aged inventory" in why
    assert "6.4 months to clear" in why
    assert "growing sales momentum" in why


def test_04_ranked_push_table_structure(sample_analysis):
    """Verify ranked Push SKU table contains all 18 Push items with required columns."""
    ranked = sample_analysis.get("ranked_push_table")
    assert ranked is not None
    assert len(ranked) == 18, f"Expected 18 Push items in ranked table, got {len(ranked)}"

    required_cols = [
        "Rank", "SKU", "Description", "Category",
        "Aged Value", "Months to Clear", "Sales Trend",
        "Risk Score", "Priority Score", "Recommended Action"
    ]
    for c in required_cols:
        assert c in ranked.columns, f"Required column '{c}' missing from ranked Push table"

    # Verify strictly ordered descending by Priority Score
    scores = ranked["Priority Score"].tolist()
    assert scores == sorted(scores, reverse=True), "Ranked table must be sorted by Priority Score descending"

    # Verify Rank 1 to 18
    assert ranked["Rank"].tolist() == list(range(1, 19))


def test_05_sku1005_top_priority_rank(sample_analysis):
    """Verify SKU1005 (highest aged inventory capital) ranks at the top of the priority queue."""
    ranked = sample_analysis["ranked_push_table"]
    top_sku = ranked.iloc[0]["SKU"]
    assert top_sku == "SKU1005", f"Expected SKU1005 to be Rank 1, got {top_sku}"

    top_item = ranked.iloc[0]
    assert top_item["Priority Score"] >= 80
    assert top_item["Priority Level"] == "Critical"
    assert "₹31,280" in top_item["Why Priority"]


def test_06_edge_case_infinite_months_to_clear():
    """Verify items with infinite Months to Clear receive maximum runway points without crashing."""
    item = {
        "Aged Value": 10000, "Inventory Value": 25000, "Months to Clear": float("inf"),
        "Sales Trend": "No Sales", "Avg Monthly Sales": 0, "Total Stock": 100,
        "Risk Score": 75
    }
    res = calculate_sales_priority_row(item)
    assert res["priority_score"] >= 60
    assert "infinite (stagnant)" in res["why_priority"]
    assert res["points_breakdown"]["months_to_clear_pts"] == 20


def test_07_edge_case_empty_dataframe():
    """Verify empty DataFrame input is handled safely."""
    empty_df = pd.DataFrame()
    res = calculate_sales_priority(empty_df)
    assert res.empty
    ranked = get_ranked_push_table(empty_df)
    assert ranked.empty
