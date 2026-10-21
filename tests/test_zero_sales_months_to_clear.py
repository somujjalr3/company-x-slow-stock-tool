"""
Automated unit and integration tests verifying zero-sales handling and division-by-zero prevention
in Months to Clear calculations and downstream modules.

Tests 1 to 9 correspond directly to user specifications:
- TEST 1: Total Stock > 0, 6M Sales Qty = 0 -> Months to Clear = np.inf (no crash)
- TEST 2: Total Stock = 0, 6M Sales Qty = 0 -> No crash
- TEST 3: 6M Sales Qty > 0 -> Months to Clear = Total Stock / Avg Monthly Sales
- TEST 4: Zero sales + aged inventory -> R5 rule order verified
- TEST 5: Zero sales + no aged inventory -> R5 rule order verified (No Action if not Red List)
- TEST 6: Dashboard data structures load successfully with zero-sales SKUs
- TEST 7: Excel export succeeds with zero-sales SKUs
- TEST 8: Risk Score works with zero-sales SKUs
- TEST 9: What-if simulation does not crash when current sales are zero
"""

import math
import numpy as np
import pandas as pd
import pytest

from src.business_logic import (
    run_analysis,
    calculate_inventory_risk,
    generate_sku_classification_explanation,
    recommend_operational_action,
    build_audit_trail,
)
from src.validation import validate_data
from src.customer_targets import build_customer_targets
from src.sales_action_center import build_sales_action_table
from src.scenario_simulator import simulate_sku_sales_uplift, simulate_portfolio_uplift
from src.export import create_excel_report
from src.config import CaseConfig, get_default_config


def _create_minimal_datasets(items_data, sales_data=None):
    """Helper to build conformant DataFrames for testing."""
    im_rows = []
    for r in items_data:
        im_rows.append({
            "SKU": r["SKU"],
            "Item Name": r.get("Item Name", f"Item {r['SKU']}"),
            "Category": r.get("Category", "General"),
            "Master Pack Qty": r.get("Master Pack Qty", 1),
            "Unit Cost (Rs)": r.get("Unit Cost (Rs)", 100),
            "Alternate Item (name)": r.get("Alternate Item (name)", None),
            "Alternate Flag": r.get("Alternate Flag", 0),
            "Status": r.get("Status", "ACTIVE"),
        })
    im = pd.DataFrame(im_rows)

    stock_rows = []
    for row in items_data:
        aged = row.get("Aged Qty", 0)
        tot = row.get("Total Stock", 0)
        fresh = max(0, tot - aged)
        stock_rows.append({
            "SKU": row["SKU"],
            "Qty 0-30 days": fresh,
            "Qty 31-60 days": 0,
            "Qty 61-90 days": 0,
            "Qty 91-180 days": aged,
            "Qty 180+ days": 0,
        })
    stock = pd.DataFrame(stock_rows)

    if sales_data is not None:
        sales = pd.DataFrame(sales_data)
    else:
        sales_rows = []
        for row in items_data:
            s_qty = row.get("6M Sales Qty", 0)
            if s_qty > 0:
                sales_rows.append({
                    "Month": pd.Timestamp("2026-03-01"),
                    "CustomerID": "C001",
                    "CustomerName": "Acme Corp",
                    "Industry": "Manufacturing",
                    "SKU": row["SKU"],
                    "Qty": s_qty,
                    "Value (Rs)": s_qty * row.get("Unit Cost (Rs)", 100),
                })
        if not sales_rows:
            sales = pd.DataFrame(columns=["Month", "CustomerID", "CustomerName", "Industry", "SKU", "Qty", "Value (Rs)"])
        else:
            sales = pd.DataFrame(sales_rows)

    cust = pd.DataFrame([
        {"CustomerID": "C001", "CustomerName": "Acme Corp", "Industry": "Manufacturing", "Area": "North"}
    ])

    return im, stock, sales, cust


def test_1_total_stock_gt_zero_zero_sales():
    """
    TEST 1:
    Total Stock > 0
    6M Sales Qty = 0
    Expected Months to Clear = infinity / safe equivalent
    Application must not crash.
    """
    im, stock, sales, cust = _create_minimal_datasets([
        {
            "SKU": "SKU_ZERO_SALES",
            "Item Name": "Test Zero Sales",
            "Category": "Tools",
            "Master Pack Qty": 10,
            "Unit Cost (Rs)": 100,
            "Total Stock": 50,
            "Aged Qty": 20,
            "6M Sales Qty": 0,
        }
    ])

    val = validate_data(im, stock, sales, cust)
    res = run_analysis(im, stock, sales, cust, val)
    items = res["analysis_items"]

    assert len(items) == 1
    row = items.iloc[0]
    assert row["Avg Monthly Sales"] == 0.0
    assert np.isinf(row["Months to Clear"])
    assert row["Months to Clear"] > 0
    assert row["Months to Clear"] == float("inf")


def test_2_total_stock_zero_zero_sales():
    """
    TEST 2:
    Total Stock = 0
    6M Sales Qty = 0
    Application must not crash.
    """
    im, stock, sales, cust = _create_minimal_datasets([
        {
            "SKU": "SKU_ZERO_STOCK_ZERO_SALES",
            "Item Name": "Test Zero Stock Zero Sales",
            "Category": "Tools",
            "Master Pack Qty": 10,
            "Unit Cost (Rs)": 100,
            "Total Stock": 0,
            "Aged Qty": 0,
            "6M Sales Qty": 0,
        }
    ])

    val = validate_data(im, stock, sales, cust)
    res = run_analysis(im, stock, sales, cust, val)
    items = res["analysis_items"]

    assert len(items) == 1
    row = items.iloc[0]
    assert row["Total Stock"] == 0
    assert row["Avg Monthly Sales"] == 0.0
    # Must be safely assigned np.inf without ZeroDivisionError
    assert np.isinf(row["Months to Clear"])


def test_3_positive_sales_months_to_clear_formula():
    """
    TEST 3:
    6M Sales Qty > 0
    Expected Months to Clear = Total Stock / Avg Monthly Sales.
    """
    im, stock, sales, cust = _create_minimal_datasets([
        {
            "SKU": "SKU_ACTIVE_SALES",
            "Item Name": "Test Active Sales",
            "Category": "Tools",
            "Master Pack Qty": 10,
            "Unit Cost (Rs)": 50,
            "Total Stock": 120,
            "Aged Qty": 30,
            "6M Sales Qty": 60,
        }
    ])

    val = validate_data(im, stock, sales, cust)
    res = run_analysis(im, stock, sales, cust, val)
    items = res["analysis_items"]

    row = items.iloc[0]
    exp_avg_monthly_sales = 60 / 6.0  # 10.0
    exp_mtc = 120 / exp_avg_monthly_sales  # 12.0
    assert row["Avg Monthly Sales"] == pytest.approx(exp_avg_monthly_sales)
    assert row["Months to Clear"] == pytest.approx(exp_mtc)


def test_4_zero_sales_plus_aged_inventory_r5_order():
    """
    TEST 4:
    Zero sales + aged inventory
    Verify R5 classification follows the exact rule order:
    1. RED LIST if 6M Sales Qty < 1 Master Pack
    2. Otherwise NO ACTION if Aged Qty = 0 OR Months to Clear < 3
    3. Otherwise PUSH
    """
    # Case 4A: Normal Master Pack Qty >= 1 -> Must be RED LIST (Rule R5 Step 1)
    im_a, stock_a, sales_a, cust_a = _create_minimal_datasets([
        {
            "SKU": "SKU_ZERO_REDLIST",
            "Item Name": "Zero Sales Standard MP",
            "Category": "Safety",
            "Master Pack Qty": 10,
            "Unit Cost (Rs)": 150,
            "Total Stock": 100,
            "Aged Qty": 50,
            "6M Sales Qty": 0,
        }
    ])
    res_a = run_analysis(im_a, stock_a, sales_a, cust_a)
    assert res_a["analysis_items"].iloc[0]["Class"] == "Red List"

    # Case 4B: If Master Pack Qty is 0 (does not trigger Red List 0 < 0):
    # Step 2: Aged Qty (50) == 0 is False; Months to Clear (inf) < 3 is False.
    # Step 3: Falls through to PUSH.
    im_b, stock_b, sales_b, cust_b = _create_minimal_datasets([
        {
            "SKU": "SKU_ZERO_PUSH_FALLTHROUGH",
            "Item Name": "Zero Sales Zero MP Fallthrough",
            "Category": "Safety",
            "Master Pack Qty": 0,
            "Unit Cost (Rs)": 150,
            "Total Stock": 100,
            "Aged Qty": 50,
            "6M Sales Qty": 0,
        }
    ])
    res_b = run_analysis(im_b, stock_b, sales_b, cust_b)
    assert res_b["analysis_items"].iloc[0]["Class"] == "Push"


def test_5_zero_sales_plus_no_aged_inventory_r5_order():
    """
    TEST 5:
    Zero sales + no aged inventory
    Verify R5 classification is NO ACTION after Red List condition is evaluated.
    """
    # If Master Pack Qty is 0 (Red List 0 < 0 is False) and Aged Qty == 0:
    # Rule R5 Step 2 (Aged Qty == 0) triggers NO ACTION.
    im, stock, sales, cust = _create_minimal_datasets([
        {
            "SKU": "SKU_ZERO_NO_AGED",
            "Item Name": "Zero Sales No Aged Stock",
            "Category": "Safety",
            "Master Pack Qty": 0,
            "Unit Cost (Rs)": 100,
            "Total Stock": 50,
            "Aged Qty": 0,
            "6M Sales Qty": 0,
        }
    ])
    res = run_analysis(im, stock, sales, cust)
    assert res["analysis_items"].iloc[0]["Class"] == "No Action"


def test_6_dashboard_loads_with_zero_sales_skus():
    """
    TEST 6:
    Verify dashboard data structures and metrics load successfully with zero-sales SKUs.
    """
    im, stock, sales, cust = _create_minimal_datasets([
        {"SKU": "SKU_Z1", "Item Name": "Z1", "Category": "Hardware", "Master Pack Qty": 10, "Unit Cost (Rs)": 100, "Total Stock": 50, "Aged Qty": 30, "6M Sales Qty": 0},
        {"SKU": "SKU_Z2", "Item Name": "Z2", "Category": "Hardware", "Master Pack Qty": 0, "Unit Cost (Rs)": 50, "Total Stock": 20, "Aged Qty": 10, "6M Sales Qty": 0},
        {"SKU": "SKU_A1", "Item Name": "A1", "Category": "Hardware", "Master Pack Qty": 5, "Unit Cost (Rs)": 80, "Total Stock": 100, "Aged Qty": 40, "6M Sales Qty": 30},
    ])
    val = validate_data(im, stock, sales, cust)
    analysis = run_analysis(im, stock, sales, cust, val)
    items = analysis["analysis_items"]
    clean_sales = analysis["clean_sales"]
    raw = (im, stock, sales, cust)

    targets = build_customer_targets(analysis["clean_item_master"], clean_sales, items, val, customers=cust)
    audit = build_audit_trail(raw, val, analysis, targets)
    sa_tbl = build_sales_action_table(items, targets, sales_trends=analysis.get("sales_trends"))

    assert len(items) == 3
    assert "Months to Clear" in items.columns
    # Check string representation for display
    disp_mtc = items["Months to Clear"].apply(lambda m: "∞" if np.isinf(m) else f"{m:.2f}")
    assert "∞" in disp_mtc.values


def test_7_excel_export_succeeds_with_zero_sales():
    """
    TEST 7:
    Verify Excel export succeeds with zero-sales SKUs without openpyxl or float formatting errors.
    """
    im, stock, sales, cust = _create_minimal_datasets([
        {"SKU": "SKU_Z1", "Item Name": "Z1", "Category": "Hardware", "Master Pack Qty": 10, "Unit Cost (Rs)": 100, "Total Stock": 50, "Aged Qty": 30, "6M Sales Qty": 0},
        {"SKU": "SKU_Z2", "Item Name": "Z2", "Category": "Hardware", "Master Pack Qty": 0, "Unit Cost (Rs)": 50, "Total Stock": 20, "Aged Qty": 10, "6M Sales Qty": 0},
    ])
    val = validate_data(im, stock, sales, cust)
    analysis = run_analysis(im, stock, sales, cust, val)
    items = analysis["analysis_items"]
    targets = build_customer_targets(analysis["clean_item_master"], analysis["clean_sales"], items, val, customers=cust)

    excel_bytes = create_excel_report(
        items=items,
        targets=targets,
        validation=val,
        inactive_stock=analysis.get("inactive_stock"),
        switches=analysis.get("switch_map_df"),
        analysis=analysis,
        sales_lines=analysis.get("clean_sales"),
    )
    assert excel_bytes is not None
    assert len(excel_bytes) > 5000  # valid multi-sheet Excel file


def test_8_risk_score_works_with_zero_sales_skus():
    """
    TEST 8:
    Verify Risk Score works with zero-sales SKUs.
    """
    im, stock, sales, cust = _create_minimal_datasets([
        {"SKU": "SKU_Z1", "Item Name": "Z1", "Category": "Hardware", "Master Pack Qty": 10, "Unit Cost (Rs)": 100, "Total Stock": 50, "Aged Qty": 30, "6M Sales Qty": 0},
        {"SKU": "SKU_Z0", "Item Name": "Z0", "Category": "Hardware", "Master Pack Qty": 10, "Unit Cost (Rs)": 100, "Total Stock": 0, "Aged Qty": 0, "6M Sales Qty": 0},
    ])
    val = validate_data(im, stock, sales, cust)
    analysis = run_analysis(im, stock, sales, cust, val)
    items = analysis["analysis_items"]

    assert "Risk Score" in items.columns
    assert "Risk Level" in items.columns
    for _, row in items.iterrows():
        assert 0 <= row["Risk Score"] <= 100
        assert row["Risk Level"] in ["Low", "Medium", "High", "Critical"]


def test_9_whatif_simulation_does_not_crash_when_sales_zero():
    """
    TEST 9:
    Verify What-if simulation does not crash when current sales are zero.
    """
    zero_sales_sku = {
        "SKU": "SKU_SIM_ZERO",
        "Item Name": "Zero Sales Simulation Test",
        "Category": "Tools",
        "Total Stock": 100,
        "Unit Cost (Rs)": 200,
        "Aged Qty": 50,
        "Aged Value": 10000,
        "Master Pack Qty": 10,
        "6M Sales Qty": 0,
        "Avg Monthly Sales": 0.0,
        "Months to Clear": np.inf,
        "Class": "Red List",
    }

    # Test single SKU uplift
    res = simulate_sku_sales_uplift(zero_sales_sku, uplift_pct=25.0)
    assert res is not None
    assert res["current_avg_monthly_sales"] == 0.0
    assert math.isinf(res["current_months_to_clear"])
    assert math.isinf(res["simulated_months_to_clear"])
    assert res["runway_reduction_months"] == 0.0

    # Test portfolio uplift
    df_items = pd.DataFrame([zero_sales_sku])
    port_res = simulate_portfolio_uplift(df_items, uplift_pct=50.0)
    assert port_res is not None
    assert len(port_res["simulated_items"]) == 1
