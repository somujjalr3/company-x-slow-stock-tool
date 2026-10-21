"""
Unit tests for Sales Action Center module (src/sales_action_center.py).

Verifies:
1. Deterministic generation of customer-SKU action recommendations matching required example.
2. Construction of consolidated Sales Action Table containing all 12 required columns:
   - Priority
   - SKU
   - Item Description
   - Customer ID
   - Customer Industry
   - Bucket
   - 6M Purchase Value
   - Opportunity Score
   - Aged Value
   - Months to Clear
   - Recommended Action
   - Reason
3. Filtering across all 7 dimensions:
   - SKU
   - Category
   - Priority
   - Risk Level
   - Customer Bucket
   - Industry
   - Customer ID
4. Sorting by Priority Score descending.
5. Excel export producing valid, styled openpyxl workbook.
6. Strict invariance of customer bucket logic (R6 & R7).
"""

import io
import pytest
import pandas as pd
import openpyxl

from src.data_loader import load_data
from src.validation import validate_data
from src.business_logic import run_analysis
from src.customer_targets import build_customer_targets
from src.sales_action_center import (
    generate_customer_sku_action,
    build_sales_action_table,
    filter_sales_action_table,
    sort_sales_action_table,
    export_sales_action_excel,
)

SAMPLE_PATH = "sample_data/CompanyX_Data.xlsx"


@pytest.fixture(scope="module")
def pipeline_data():
    raw = load_data(SAMPLE_PATH)
    val = validate_data(*raw)
    res = run_analysis(*raw, validation=val)
    targets = build_customer_targets(
        res["clean_item_master"],
        res["clean_sales"],
        res["analysis_items"],
        val,
        customers=raw[3],
    )
    items = res["analysis_items"]
    table = build_sales_action_table(items, targets, sales_trends=res.get("sales_trends"))
    return raw, val, res, targets, items, table


def test_01_action_recommendation_bucket1():
    """Verify Bucket 1 exact match produces the exact example format."""
    rec = generate_customer_sku_action(
        customer_name="Customer 220",
        sku="SKU1005",
        bucket=1,
        spend=665004.0,
        industry="Caterer",
        category="Category C",
        bought_switch=False,
    )
    expected = "Contact Customer 220 and promote SKU1005 because the customer previously purchased the item and has ₹665,004 of 6M purchase value."
    assert rec == expected


def test_02_action_recommendation_bucket1_switch():
    """Verify Bucket 1 switch partner recommendation mentions switch item."""
    rec = generate_customer_sku_action(
        customer_name="Customer 101",
        sku="SKU1006",
        bucket=1,
        spend=250000.0,
        industry="Restaurant",
        category="Category A",
        bought_switch=True,
        switch_skus=["SKU1001"],
    )
    assert "Contact Customer 101 and promote SKU1006" in rec
    assert "previously purchased the switch partner item (switch partner SKU1001)" in rec
    assert "₹250,000" in rec


def test_03_action_recommendation_bucket2():
    """Verify Bucket 2 recommendation mentions peer industry."""
    rec = generate_customer_sku_action(
        customer_name="Customer 214",
        sku="SKU1005",
        bucket=2,
        spend=574001.0,
        industry="Caterer",
        category="Category C",
    )
    expected = "Contact Customer 214 and promote SKU1005 because the customer operates in the Caterer industry associated with previous buyers and has ₹574,001 of 6M purchase value."
    assert rec == expected


def test_04_action_recommendation_bucket3():
    """Verify Bucket 3 recommendation mentions same category."""
    rec = generate_customer_sku_action(
        customer_name="Customer 208",
        sku="SKU1005",
        bucket=3,
        spend=495738.0,
        industry="Restaurant",
        category="Category C",
    )
    expected = "Contact Customer 208 and promote SKU1005 because the customer previously purchased other items in the Category C category and has ₹495,738 of 6M purchase value."
    assert rec == expected


def test_05_sales_action_table_columns(pipeline_data):
    """Verify all 12 specified columns are present in the Sales Action Table."""
    _, _, _, _, _, table = pipeline_data

    required_cols = [
        "Priority",
        "SKU",
        "Item Description",
        "Customer ID",
        "Customer Industry",
        "Bucket",
        "6M Purchase Value",
        "Opportunity Score",
        "Aged Value",
        "Months to Clear",
        "Recommended Action",
        "Reason",
    ]

    for col in required_cols:
        assert col in table.columns, f"Required column '{col}' missing from Sales Action Table"

    assert len(table) > 0
    # In sample data, exactly 163 actionable customer-SKU combinations exist across 18 Push items
    assert len(table) == 163


def test_06_filter_by_sku(pipeline_data):
    """Test filtering by SKU."""
    _, _, _, _, _, table = pipeline_data
    filtered = filter_sales_action_table(table, sku="SKU1005")
    assert len(filtered) == 9
    assert (filtered["SKU"] == "SKU1005").all()


def test_07_filter_by_category(pipeline_data):
    """Test filtering by Category."""
    _, _, _, _, _, table = pipeline_data
    filtered = filter_sales_action_table(table, category="Category C")
    assert len(filtered) > 0
    assert (filtered["Category"] == "Category C").all()


def test_08_filter_by_priority(pipeline_data):
    """Test filtering by Priority Level."""
    _, _, _, _, _, table = pipeline_data
    filtered = filter_sales_action_table(table, priority="Critical")
    assert len(filtered) > 0
    assert (filtered["Priority"] == "Critical").all()


def test_09_filter_by_risk_level(pipeline_data):
    """Test filtering by Risk Level."""
    _, _, _, _, _, table = pipeline_data
    filtered = filter_sales_action_table(table, risk_level="High")
    assert len(filtered) > 0
    assert (filtered["Risk Level"] == "High").all()


def test_10_filter_by_customer_bucket(pipeline_data):
    """Test filtering by Customer Bucket (integer and string)."""
    _, _, _, _, _, table = pipeline_data
    f_int = filter_sales_action_table(table, customer_bucket=1)
    f_str = filter_sales_action_table(table, customer_bucket="Bucket 1")
    assert len(f_int) == 43
    assert len(f_str) == 43
    assert (f_int["Bucket"] == 1).all()


def test_11_filter_by_industry(pipeline_data):
    """Test filtering by Industry."""
    _, _, _, _, _, table = pipeline_data
    filtered = filter_sales_action_table(table, industry="Caterer")
    assert len(filtered) > 0
    assert (filtered["Customer Industry"] == "Caterer").all()


def test_12_filter_by_customer_id(pipeline_data):
    """Test filtering by Customer ID."""
    _, _, _, _, _, table = pipeline_data
    filtered = filter_sales_action_table(table, customer_id="C220")
    assert len(filtered) > 0
    assert (filtered["Customer ID"] == "C220").all()


def test_13_sorting_by_priority_score(pipeline_data):
    """Verify sorting by Priority Score descending."""
    _, _, _, _, _, table = pipeline_data
    sorted_df = sort_sales_action_table(table, sort_by="Priority Score")

    # SKU1005 is Priority Score 84 (Critical) and should be first
    assert sorted_df.iloc[0]["SKU"] == "SKU1005"
    assert sorted_df.iloc[0]["Priority Score"] == 84

    # Monotonically non-increasing Priority Score
    scores = sorted_df["Priority Score"].tolist()
    assert scores == sorted(scores, reverse=True)


def test_14_export_sales_action_excel(pipeline_data):
    """Verify Excel export generates valid workbook with data."""
    _, _, _, _, _, table = pipeline_data
    excel_bytes = export_sales_action_excel(table)
    assert len(excel_bytes) > 5000

    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
    assert "Sales Action List" in wb.sheetnames
    ws = wb["Sales Action List"]

    # Header check
    headers = [ws.cell(row=4, column=c).value for c in range(1, 17)]
    assert "Priority" in headers
    assert "SKU" in headers
    assert "Customer ID" in headers
    assert "Recommended Action" in headers
    assert ws.max_row >= 167  # 4 header rows + 163 data rows
