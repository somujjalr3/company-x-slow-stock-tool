"""
Tests for Working Capital Impact module and Cash at Risk calculations.
Verifies:
  1. Total Inventory Value = Total Stock × Unit Cost
  2. Aged Inventory Value = Aged Qty × Unit Cost (Cash at Risk)
  3. Aged Inventory % = Aged Inventory Value / Total Inventory Value
  4. Push Inventory Value
  5. Red List Inventory Value
  6. No Action Inventory Value
  7. High-risk SKU count
  8. Cash at Risk disclosure labeling
  9. Breakdown structures (by class, by category, top 10 SKUs)
  10. Zero stock and edge cases
  11. Source-of-truth R1-R7 classification invariance
"""
import pytest
import pandas as pd
import numpy as np

from src.business_logic import run_analysis, calculate_working_capital_impact
from src.data_loader import load_data

SAMPLE_PATH = "sample_data/CompanyX_Data.xlsx"


def test_working_capital_formula_exactness():
    """Verify all mathematical formulas across active catalog items."""
    # Synthetic dataset with known deterministic numbers
    items = pd.DataFrame([
        {
            "SKU": "SKU_P1", "Item Name": "Push Item 1", "Category": "Cat A", "Class": "Push",
            "Total Stock": 100, "Aged Qty": 40, "Unit Cost (Rs)": 50, "Risk Level": "High"
        },
        {
            "SKU": "SKU_P2", "Item Name": "Push Item 2", "Category": "Cat B", "Class": "Push",
            "Total Stock": 200, "Aged Qty": 60, "Unit Cost (Rs)": 20, "Risk Level": "Medium"
        },
        {
            "SKU": "SKU_RL", "Item Name": "Red List Item", "Category": "Cat A", "Class": "Red List",
            "Total Stock": 50, "Aged Qty": 50, "Unit Cost (Rs)": 30, "Risk Level": "Critical"
        },
        {
            "SKU": "SKU_NA", "Item Name": "No Action Item", "Category": "Cat B", "Class": "No Action",
            "Total Stock": 300, "Aged Qty": 0, "Unit Cost (Rs)": 10, "Risk Level": "Low"
        },
    ])
    # Expected:
    # P1:  Stock Val = 5000, Aged Val = 2000
    # P2:  Stock Val = 4000, Aged Val = 1200
    # RL:  Stock Val = 1500, Aged Val = 1500
    # NA:  Stock Val = 3000, Aged Val = 0
    # Total Inv = 5000 + 4000 + 1500 + 3000 = 13500
    # Total Aged = 2000 + 1200 + 1500 + 0 = 4700
    # Push Inv = 9000, Push Aged = 3200
    # Red Inv = 1500, Red Aged = 1500
    # NA Inv = 3000, NA Aged = 0
    # Aged % = 4700 / 13500 * 100 = 34.8148%
    # High Risk SKUs = 2 (Critical + High)

    wc = calculate_working_capital_impact(items)
    s = wc["summary"]

    assert s["total_inventory_value"] == pytest.approx(13500.0)
    assert s["aged_inventory_value"] == pytest.approx(4700.0)
    assert s["cash_at_risk"] == pytest.approx(4700.0)
    assert s["aged_inventory_pct"] == pytest.approx(4700.0 / 13500.0 * 100.0)

    assert s["push_inventory_value"] == pytest.approx(9000.0)
    assert s["red_list_inventory_value"] == pytest.approx(1500.0)
    assert s["no_action_inventory_value"] == pytest.approx(3000.0)

    assert s["push_aged_value"] == pytest.approx(3200.0)
    assert s["red_list_aged_value"] == pytest.approx(1500.0)
    assert s["no_action_aged_value"] == pytest.approx(0.0)

    # Cross-tier additivity proofs
    assert s["push_inventory_value"] + s["red_list_inventory_value"] + s["no_action_inventory_value"] == pytest.approx(s["total_inventory_value"])
    assert s["push_aged_value"] + s["red_list_aged_value"] + s["no_action_aged_value"] == pytest.approx(s["aged_inventory_value"])

    # High-risk count
    assert s["high_risk_sku_count"] == 2


def test_cash_at_risk_concept_and_labeling():
    """Verify Cash at Risk concept uses Aged Inventory Value and has clear non-guarantee disclosure."""
    raw = load_data(SAMPLE_PATH)
    analysis = run_analysis(*raw)
    wc = analysis["working_capital"]
    s = wc["summary"]

    assert s["cash_at_risk"] == s["aged_inventory_value"]
    assert "not guaranteed cash recovery" in s["cash_at_risk_note"].lower()
    assert "aged stock" in s["cash_at_risk_note"].lower()


def test_sample_case_benchmarks_working_capital():
    """Verify exact working capital benchmark numbers on official sample data."""
    raw = load_data(SAMPLE_PATH)
    analysis = run_analysis(*raw)
    items = analysis["analysis_items"]
    wc = analysis["working_capital"]
    s = wc["summary"]

    # Benchmark verifications
    assert s["total_inventory_value"] == pytest.approx(906525.0)
    assert s["aged_inventory_value"] == pytest.approx(237616.0)
    assert s["cash_at_risk"] == pytest.approx(237616.0)
    assert s["aged_inventory_pct"] == pytest.approx(237616.0 / 906525.0 * 100.0, rel=1e-3)

    assert s["push_inventory_value"] == pytest.approx(558169.0)
    assert s["push_aged_value"] == pytest.approx(163841.0)  # Matches R5 Push Aged Value benchmark!

    assert s["red_list_inventory_value"] == pytest.approx(109270.0)
    assert s["red_list_aged_value"] == pytest.approx(32815.0)

    assert s["no_action_inventory_value"] == pytest.approx(239086.0)
    assert s["no_action_aged_value"] == pytest.approx(40960.0)

    # 100% additivity check
    assert s["push_inventory_value"] + s["red_list_inventory_value"] + s["no_action_inventory_value"] == pytest.approx(906525.0)
    assert s["push_aged_value"] + s["red_list_aged_value"] + s["no_action_aged_value"] == pytest.approx(237616.0)

    # 9 high-risk SKUs in sample dataset
    assert s["high_risk_sku_count"] == 9


def test_working_capital_breakdown_structures():
    """Verify breakdown structures for charts: by class, by category, and top 10 SKUs."""
    raw = load_data(SAMPLE_PATH)
    analysis = run_analysis(*raw)
    wc = analysis["working_capital"]

    by_class = wc["by_class"]
    by_cat = wc["by_category"]
    top10 = wc["top10_aged_skus"]

    # 1. By Class
    assert set(by_class["Class"].tolist()) == {"Push", "No Action", "Red List"}
    assert "Inventory Value" in by_class.columns
    assert "Aged Value" in by_class.columns
    assert "Aged Share %" in by_class.columns

    # 2. By Category
    assert len(by_cat) == 6
    assert "Category" in by_cat.columns
    assert "Aged Value" in by_cat.columns
    assert by_cat["Aged Value"].sum() == pytest.approx(237616.0)

    # 3. Top 10 SKUs
    assert len(top10) == 10
    assert top10.iloc[0]["SKU"] == "SKU1005"
    assert top10.iloc[0]["Aged Value"] == pytest.approx(31280.0)
    assert (top10["Aged Value"].diff().dropna() <= 0).all()  # Monotonically descending


def test_empty_and_zero_stock_edge_cases():
    """Verify working capital calculations on empty DataFrames and zero stock."""
    empty_df = pd.DataFrame()
    wc_empty = calculate_working_capital_impact(empty_df)
    assert wc_empty["summary"]["total_inventory_value"] == 0.0
    assert wc_empty["summary"]["aged_inventory_value"] == 0.0
    assert wc_empty["summary"]["aged_inventory_pct"] == 0.0

    # Zero stock but positive cost
    zero_stock_df = pd.DataFrame([{
        "SKU": "S1", "Item Name": "P1", "Category": "Cat A", "Class": "No Action",
        "Total Stock": 0, "Aged Qty": 0, "Unit Cost (Rs)": 150, "Risk Level": "Low"
    }])
    wc_zero = calculate_working_capital_impact(zero_stock_df)
    assert wc_zero["summary"]["total_inventory_value"] == 0.0
    assert wc_zero["summary"]["aged_inventory_value"] == 0.0
    assert wc_zero["summary"]["aged_inventory_pct"] == 0.0


def test_r1_to_r7_invariance():
    """Verify that working capital calculations strictly preserve R1-R7 rules and classification counts."""
    raw = load_data(SAMPLE_PATH)
    analysis = run_analysis(*raw)
    items = analysis["analysis_items"]

    counts = items["Class"].value_counts()
    assert counts["Red List"] == 7
    assert counts["No Action"] == 13
    assert counts["Push"] == 18

    # Spot checks
    sku_classes = items.set_index("SKU")["Class"].to_dict()
    assert sku_classes["SKU1001"] == "No Action"
    assert sku_classes["SKU1006"] == "Push"
    assert sku_classes["SKU1019"] == "Push"
    assert sku_classes["SKU1005"] == "Push"
