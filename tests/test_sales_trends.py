"""
Unit Tests for Sales Trend Analysis Module.

Tests:
  1. Calculation of monthly sales quantity and monthly sales value.
  2. Average monthly sales, latest month sales, and previous month sales.
  3. Sales growth/decline percentage and quantity.
  4. Deterministic classification of trends:
       - Growing (> +5.0% MoM)
       - Stable (within [-5.0%, +5.0%])
       - Declining (< -5.0% MoM, or drop to 0)
       - No Sales (zero historical sales)
       - Insufficient Data (historical periods < 2 months, no fabricated data)
  5. Top declining Push items and Top growing Push items ranking functions.
  6. Strict R1-R7 Invariance:
       - Red List = 7
       - No Action = 13
       - Push = 18
       - Push Aged Value = 163,841
       - SKU1001 = No Action
       - SKU1006 = Push
       - SKU1019 = Push
       - SKU1005 = Push
  7. Clear distinction: Case Classification vs Sales Trend (orthogonal metrics).
  8. SWITCH consolidation under new SKU.
  9. Edge cases (single month, empty data, 0 to positive, positive to 0).
"""

import pytest
import numpy as np
import pandas as pd

from src.data_loader import load_workbook
from src.business_logic import run_analysis
from src.sales_trends import (
    calculate_monthly_sales_trends,
    get_top_declining_push_items,
    get_top_growing_push_items,
    parse_and_sort_months,
)


@pytest.fixture(scope="module")
def sample_analysis():
    im, st, sl, cu = load_workbook("sample_data/CompanyX_Data.xlsx")
    return run_analysis(im, st, sl, cu)


def test_01_core_rules_r1_to_r7_invariant(sample_analysis):
    """Confirm Sales Trend module preserves all core R1-R7 benchmarks exactly."""
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


def test_02_month_chronological_ordering():
    """Verify months with diverse date formats are parsed in strict chronological order."""
    months = ["Aug-2026", "Apr-2026", "2026-06", "Sep-2026", "May-2026", "Jul-2026"]
    ordered, _ = parse_and_sort_months(months)
    expected = ["Apr-2026", "May-2026", "2026-06", "Jul-2026", "Aug-2026", "Sep-2026"]
    assert ordered == expected, f"Expected {expected}, got {ordered}"


def test_03_monthly_sales_metrics_calculation(sample_analysis):
    """Verify monthly quantity, value, average, latest, and previous month sales."""
    trends = sample_analysis["sales_trends"]
    assert trends is not None
    assert trends["period_count"] == 6

    trends_by_sku = trends["trends_by_sku"]

    # Test SKU1005 (Push, Growing)
    t_1005 = trends_by_sku["SKU1005"]
    assert t_1005["total_qty"] == 280.0
    assert t_1005["latest_month"] == "Sep-2026"
    assert t_1005["prev_month"] == "Aug-2026"
    assert t_1005["latest_qty"] == 58.0
    assert t_1005["prev_qty"] == 42.0
    assert t_1005["growth_qty"] == 16.0
    # Growth = (58 - 42) / 42 = +38.095%
    assert pytest.approx(t_1005["growth_pct"], rel=1e-2) == 38.10
    assert t_1005["sales_trend"] == "Growing"


def test_04_trend_classifications_in_sample_data(sample_analysis):
    """Verify sample dataset distribution and classifications for key SKUs."""
    trends = sample_analysis["sales_trends"]
    dist = trends["distribution"]

    # Verify that all 5 categories are tracked
    for cat in ["Growing", "Stable", "Declining", "No Sales", "Insufficient Data"]:
        assert cat in dist

    trends_by_sku = trends["trends_by_sku"]

    # SKU1005 is Growing (42 -> 58, +38.1%)
    assert trends_by_sku["SKU1005"]["sales_trend"] == "Growing"

    # SKU1006 is Stable (55 -> 56, +1.8% within +/- 5%)
    assert trends_by_sku["SKU1006"]["sales_trend"] == "Stable"
    assert pytest.approx(trends_by_sku["SKU1006"]["growth_pct"], rel=1e-2) == 1.82

    # SKU1019 is Declining (197 -> 187, -5.08%)
    assert trends_by_sku["SKU1019"]["sales_trend"] == "Declining"

    # SKU1012 has 0 sales -> No Sales
    assert trends_by_sku["SKU1012"]["sales_trend"] == "No Sales"
    assert trends_by_sku["SKU1012"]["total_qty"] == 0.0


def test_05_insufficient_data_single_period():
    """Verify no data fabrication when fewer than 2 historical months are available."""
    single_month_sl = pd.DataFrame([
        {"SKU": "SKU9001", "Month": "Sep-2026", "Qty": 80, "Value (Rs)": 2000},
        {"SKU": "SKU9002", "Month": "Sep-2026", "Qty": 0, "Value (Rs)": 0},
    ])
    res = calculate_monthly_sales_trends(single_month_sl)

    assert res["period_count"] == 1
    t_9001 = res["trends_by_sku"]["SKU9001"]
    assert t_9001["sales_trend"] == "Insufficient Data"
    assert t_9001["latest_qty"] == 80.0
    assert t_9001["prev_qty"] is None
    assert t_9001["growth_pct"] is None
    assert t_9001["sufficient_data"] is False
    assert "minimum of 2 chronological months is required" in t_9001["trend_reason"]

    # SKU9002 had 0 sales
    t_9002 = res["trends_by_sku"]["SKU9002"]
    assert t_9002["sales_trend"] == "No Sales"


def test_06_edge_case_jump_from_zero_to_positive():
    """Verify SKU emerging from zero sales in previous month is classified as Growing."""
    two_month_sl = pd.DataFrame([
        {"SKU": "SKUX", "Month": "Aug-2026", "Qty": 0, "Value (Rs)": 0},
        {"SKU": "SKUX", "Month": "Sep-2026", "Qty": 25, "Value (Rs)": 500},
    ])
    res = calculate_monthly_sales_trends(two_month_sl)
    t = res["trends_by_sku"]["SKUX"]
    assert t["sales_trend"] == "Growing"
    assert t["growth_qty"] == 25.0
    assert t["growth_pct"] == 100.0


def test_07_edge_case_drop_from_positive_to_zero():
    """Verify SKU dropping from positive sales to zero is classified as Declining."""
    two_month_sl = pd.DataFrame([
        {"SKU": "SKUY", "Month": "Aug-2026", "Qty": 30, "Value (Rs)": 600},
        {"SKU": "SKUY", "Month": "Sep-2026", "Qty": 0, "Value (Rs)": 0},
    ])
    res = calculate_monthly_sales_trends(two_month_sl)
    t = res["trends_by_sku"]["SKUY"]
    assert t["sales_trend"] == "Declining"
    assert t["growth_qty"] == -30.0
    assert t["growth_pct"] == -100.0


def test_08_edge_case_zero_in_both_recent_months_with_prior_sales():
    """Verify SKU with 0 sales in last 2 months but earlier sales is classified as Declining."""
    three_month_sl = pd.DataFrame([
        {"SKU": "SKUZ", "Month": "Jul-2026", "Qty": 10, "Value (Rs)": 200},
        {"SKU": "SKUZ", "Month": "Aug-2026", "Qty": 0, "Value (Rs)": 0},
        {"SKU": "SKUZ", "Month": "Sep-2026", "Qty": 0, "Value (Rs)": 0},
    ])
    res = calculate_monthly_sales_trends(three_month_sl)
    t = res["trends_by_sku"]["SKUZ"]
    assert t["sales_trend"] == "Declining"
    assert t["total_qty"] == 10.0


def test_09_top_declining_and_growing_push_items(sample_analysis):
    """Verify top declining and top growing Push ranking helpers."""
    items = sample_analysis["analysis_items"]
    trends = sample_analysis["sales_trends"]
    summary_df = trends["summary_df"]

    top_dec = get_top_declining_push_items(summary_df, items, top_n=5)
    assert len(top_dec) == 5
    # Verify all returned items are Push
    assert (top_dec["Class"] == "Push").all()
    # Verify sorted ascending by growth % (most negative first)
    growths = top_dec["Sales Growth %"].tolist()
    assert growths == sorted(growths)

    top_grow = get_top_growing_push_items(summary_df, items, top_n=5)
    assert len(top_grow) == 5
    # Verify all returned items are Push
    assert (top_grow["Class"] == "Push").all()
    # Verify sorted descending by growth % (highest positive first)
    grow_growths = top_grow["Sales Growth %"].tolist()
    assert grow_growths == sorted(grow_growths, reverse=True)


def test_10_case_classification_vs_sales_trend_distinction(sample_analysis):
    """
    Verify clear distinction between CASE CLASSIFICATION and SALES TREND.
    Confirm they are orthogonal decision-support dimensions:
    - Push items can be Growing, Stable, or Declining.
    - No Action items can be Growing or Declining.
    """
    items = sample_analysis["analysis_items"]
    push_items = items[items["Class"] == "Push"]

    push_trends = push_items["Sales Trend"].value_counts().to_dict()
    # Push items have both Growing and Declining members
    assert push_trends.get("Growing", 0) > 0
    assert push_trends.get("Declining", 0) > 0
    assert push_trends.get("Stable", 0) > 0  # SKU1006 is Stable

    # Red List item SKU1012 has No Sales
    red_items = items[items["Class"] == "Red List"]
    assert (red_items.loc[red_items["SKU"] == "SKU1012", "Sales Trend"] == "No Sales").all()


def test_11_switch_sku_sales_consolidation(sample_analysis):
    """Verify sales of old switch SKU are consolidated under the new SKU (Rule R3)."""
    items = sample_analysis["analysis_items"]
    trends = sample_analysis["sales_trends"]
    trends_by_sku = trends["trends_by_sku"]

    # SKU1019 is the consolidated switch SKU
    assert "SKU1019" in trends_by_sku
    t_1019 = trends_by_sku["SKU1019"]
    # 6M sales quantity of SKU1019 in items matches total_qty in trends
    item_1019_sales = items.loc[items["SKU"] == "SKU1019", "6M Sales Qty"].values[0]
    assert t_1019["total_qty"] == item_1019_sales
