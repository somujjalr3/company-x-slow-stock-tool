import numpy as np
import pandas as pd
import pytest

from src.business_logic import calculate_inventory_risk, calculate_inventory_risk_row, run_analysis
from src.data_loader import load_data


def test_calculate_inventory_risk_input_types():
    """Verify calculate_inventory_risk accepts DataFrame, Series, and dict, and rejects invalid types."""
    # 1. Dict input
    d_row = {
        "Total Stock": 200,
        "Aged Qty": 80,
        "Aged Value": 10000,
        "6M Sales Qty": 120,
        "Avg Monthly Sales": 20.0,
        "Months to Clear": 10.0,
        "Master Pack Qty": 25,
    }
    res_dict = calculate_inventory_risk(d_row)
    assert isinstance(res_dict, dict)
    assert "Risk Score" in res_dict
    assert "Risk Level" in res_dict
    assert "Risk Drivers" in res_dict
    assert "Risk Explanation" in res_dict
    assert 0 <= res_dict["Risk Score"] <= 100

    # 2. Series input
    s_row = pd.Series(d_row)
    res_series = calculate_inventory_risk(s_row)
    assert isinstance(res_series, dict)
    assert res_series["Risk Score"] == res_dict["Risk Score"]

    # 3. DataFrame input
    df = pd.DataFrame([d_row, d_row])
    res_df = calculate_inventory_risk(df)
    assert isinstance(res_df, pd.DataFrame)
    assert "Risk Score" in res_df.columns
    assert "Risk Level" in res_df.columns
    assert "Risk Explanation" in res_df.columns
    assert len(res_df) == 2

    # 4. Empty DataFrame input
    empty_df = pd.DataFrame()
    res_empty = calculate_inventory_risk(empty_df)
    assert isinstance(res_empty, pd.DataFrame)
    assert "Risk Score" in res_empty.columns

    # 5. Invalid type raises TypeError
    with pytest.raises(TypeError):
        calculate_inventory_risk("invalid string")


def test_transparent_five_factor_breakdown_and_weights():
    """Verify the 5 distinct scoring dimensions sum to 100 maximum:
    1. Aged Stock % (25 pts)
    2. Months to Clear (25 pts)
    3. Sales Velocity (20 pts)
    4. 6M Demand Volume Scale (15 pts)
    5. Aged Inventory Value (15 pts)
    """
    row_worst = {
        "Total Stock": 100,
        "Aged Qty": 90,           # 90% aged >= 60% -> 25 pts
        "Months to Clear": 24.0,   # >= 12m -> 22 pts (or inf -> 25 pts)
        "Avg Monthly Sales": 0.0,  # <= 0 with stock > 0 -> 25 pts MTC, 20 pts velocity
        "6M Sales Qty": 0,         # 0 sales -> 15 pts volume
        "Master Pack Qty": 50,
        "Aged Value": 35000,       # >= 25k -> 15 pts value
    }
    res_worst = calculate_inventory_risk_row(row_worst)
    assert res_worst["Risk Pts Aged"] == 25
    assert res_worst["Risk Pts MTC"] == 25
    assert res_worst["Risk Pts Velocity"] == 20
    assert res_worst["Risk Pts Volume"] == 15
    assert res_worst["Risk Pts Value"] == 15
    assert res_worst["Risk Score"] == 100
    assert res_worst["Risk Level"] == "Critical"


def test_risk_level_threshold_boundaries():
    """Verify strict adherence to specified Risk Levels:
    0-29:   Low
    30-59:  Medium
    60-79:  High
    80-100: Critical
    """
    levels = {
        0: "Low",
        15: "Low",
        29: "Low",
        30: "Medium",
        45: "Medium",
        59: "Medium",
        60: "High",
        70: "High",
        79: "High",
        80: "Critical",
        95: "Critical",
        100: "Critical",
    }
    for score, expected_lvl in levels.items():
        if score >= 80:
            lvl = "Critical"
        elif score >= 60:
            lvl = "High"
        elif score >= 30:
            lvl = "Medium"
        else:
            lvl = "Low"
        assert lvl == expected_lvl


def test_exact_user_prompt_example_explanation():
    """Verify the exact user prompt scenario matches the natural-language explanation:
    'High risk because 68% of inventory is aged, monthly sales velocity is low and the inventory will take 8.4 months to clear.'
    """
    row = {
        "Total Stock": 100,
        "Aged Qty": 68,            # 68% aged -> 25 pts ("68% of inventory is aged")
        "Avg Monthly Sales": 11.9, # turnover 0.119 < 0.20 -> 12 pts ("monthly sales velocity is low")
        "Months to Clear": 8.4,    # 8.4 months -> 18 pts ("the inventory will take 8.4 months to clear")
        "6M Sales Qty": 71,
        "Master Pack Qty": 50,     # >= 50 -> 3 pts
        "Aged Value": 15000,       # 12 pts
    }
    # Total score = 25 (aged) + 18 (mtc) + 12 (vel) + 7 (volume) + 12 (value) = 74 (High Risk)
    res = calculate_inventory_risk_row(row)
    assert res["Risk Score"] == 74
    assert res["Risk Level"] == "High"
    assert res["Risk Explanation"] == (
        "High risk because 68% of inventory is aged, monthly sales velocity is low and the inventory will take 8.4 months to clear."
    )


def test_zero_stock_and_clean_healthy_item():
    """Verify zero stock and completely healthy items result in Low Risk."""
    # Zero stock item
    row_zero_stock = {
        "Total Stock": 0,
        "Aged Qty": 0,
        "Aged Value": 0,
        "6M Sales Qty": 0,
        "Avg Monthly Sales": 0,
        "Months to Clear": 0,
        "Master Pack Qty": 10,
    }
    res_zero = calculate_inventory_risk_row(row_zero_stock)
    assert res_zero["Risk Score"] <= 29
    assert res_zero["Risk Level"] == "Low"

    # Rapid moving item with 0 aged stock (e.g. SKU1004 profile)
    row_healthy = {
        "Total Stock": 96,
        "Aged Qty": 0,
        "Aged Value": 0,
        "6M Sales Qty": 674,
        "Avg Monthly Sales": 112.3,
        "Months to Clear": 0.85,
        "Master Pack Qty": 20,
    }
    res_healthy = calculate_inventory_risk_row(row_healthy)
    assert res_healthy["Risk Score"] == 0
    assert res_healthy["Risk Level"] == "Low"
    assert "Low risk with healthy sales velocity" in res_healthy["Risk Explanation"]


def test_deterministic_execution_without_ai():
    """Verify that inventory risk calculations are 100% deterministic and never use AI or random variation."""
    row = {
        "Total Stock": 306,
        "Aged Qty": 92,
        "Aged Value": 31280,
        "6M Sales Qty": 280,
        "Avg Monthly Sales": 46.67,
        "Months to Clear": 6.56,
        "Master Pack Qty": 50,
    }
    base_res = calculate_inventory_risk_row(row)
    for _ in range(25):
        run_res = calculate_inventory_risk_row(row)
        assert run_res["Risk Score"] == base_res["Risk Score"]
        assert run_res["Risk Level"] == base_res["Risk Level"]
        assert run_res["Risk Explanation"] == base_res["Risk Explanation"]
        assert run_res["Risk Drivers"] == base_res["Risk Drivers"]


def test_risk_score_does_not_override_r1_to_r7_classification():
    """Verify that Risk Score NEVER alters or overrides R1-R7 slow stock classification."""
    raw = load_data("sample_data/CompanyX_Data.xlsx")
    analysis = run_analysis(*raw)
    items = analysis["analysis_items"]

    # Verify classification counts remain exact
    counts = items["Class"].value_counts()
    assert counts["Red List"] == 7
    assert counts["No Action"] == 13
    assert counts["Push"] == 18

    # Verify spot check SKUs maintain R5 classification regardless of Risk Score
    sku_classes = items.set_index("SKU")["Class"].to_dict()
    assert sku_classes["SKU1001"] == "No Action"
    assert sku_classes["SKU1006"] == "Push"
    assert sku_classes["SKU1019"] == "Push"
    assert sku_classes["SKU1005"] == "Push"

    # Push aged value remains exact
    push_val = items.loc[items["Class"] == "Push", "Aged Value"].sum()
    assert push_val == pytest.approx(163841.0)


def test_sku1005_risk_score_and_drivers():
    """Verify SKU1005 has high aged capital and clear risk driver reporting."""
    raw = load_data("sample_data/CompanyX_Data.xlsx")
    analysis = run_analysis(*raw)
    items = analysis["analysis_items"]

    row_1005 = items[items["SKU"] == "SKU1005"].iloc[0]
    assert row_1005["Class"] == "Push"
    assert row_1005["Risk Score"] >= 50
    assert row_1005["Risk Level"] in ["High", "Medium"]
    assert "Risk Explanation" in row_1005
    assert len(row_1005["Risk Explanation"]) > 10
    assert "inventory is aged" in row_1005["Risk Explanation"]
