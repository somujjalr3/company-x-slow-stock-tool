"""
Automated Comprehensive Test Suite for Company X Slow Stock Action Tool.

Covers all 22 core business & technical specifications plus regression tests:
1. Required sheet validation
2. Missing column validation
3. SKU standardisation
4. Duplicate sales handling
5. SWITCH consolidation
6. Inactive item exclusion
7. Inactive item stock reporting
8. Aged quantity calculation
9. Aged value calculation
10. Average monthly sales
11. Months to Clear
12. Red List classification
13. No Action classification
14. Push classification
15. Zero-sales edge case
16. Customer eligibility (> 100k)
17. Bucket 1 (Bought Before)
18. Bucket 2 (Similar Industry)
19. Missing Industry exclusion from Bucket 2
20. Bucket 3 (Same Category)
21. Bucket priority sorting (Bucket ASC, 6M Spend DESC)
22. No duplicate customer across buckets (Mutual exclusivity)

Regression Benchmarks:
- Red List = 7
- No Action = 13
- Push = 18
- Push Aged Value = 163,841
- SKU1001 = No Action
- SKU1006 = Push
- SKU1019 = Push
- SKU1005 = Push
"""
import io
import numpy as np
import pandas as pd
import pytest

from src.data_loader import load_workbook, load_data, REQUIRED_SHEETS
from src.validation import validate_data
from src.business_logic import run_analysis, build_switch_map
from src.customer_targets import build_customer_targets

SAMPLE_PATH = "sample_data/CompanyX_Data.xlsx"


# ==============================================================================
# 1. REQUIRED SHEET VALIDATION
# ==============================================================================
def test_01_required_sheet_validation():
    """Verify that omitting any of the 4 required sheets raises a descriptive ValueError."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf) as writer:
        pd.DataFrame({"a": [1]}).to_excel(writer, sheet_name="Item_Master", index=False)
        pd.DataFrame({"b": [2]}).to_excel(writer, sheet_name="Stock_Aging", index=False)
        # Omit Sales_Lines and Customers
    buf.seek(0)

    with pytest.raises(ValueError, match="missing required sheet"):
        load_workbook(buf)


# ==============================================================================
# 2. MISSING COLUMN VALIDATION
# ==============================================================================
def test_02_missing_column_validation():
    """Verify that omitting required columns from any sheet raises a clear ValueError."""
    raw = load_workbook(SAMPLE_PATH)
    im, stock, sales, cust = [df.copy() for df in raw]

    # Drop required column from Item_Master
    im_bad = im.drop(columns=["Unit Cost (Rs)"])
    with pytest.raises(ValueError, match="Item_Master is missing columns"):
        validate_data(im_bad, stock, sales, cust)

    # Drop required column from Customers
    cust_bad = cust.drop(columns=["CustomerID"])
    with pytest.raises(ValueError, match="Customers is missing columns"):
        validate_data(im, stock, sales, cust_bad)


# ==============================================================================
# 3. SKU STANDARDISATION
# ==============================================================================
def test_03_sku_standardisation():
    """Verify that SKUs with whitespace and inconsistent casing are trimmed and converted to uppercase."""
    raw = load_workbook(SAMPLE_PATH)
    im, stock, sales, cust = [df.copy() for df in raw]

    # Inject dirty formatting in sales
    sales.loc[0, "SKU"] = "  sku1001  "
    sales.loc[1, "SKU"] = "sku1002"

    val = validate_data(im, stock, sales, cust)

    # Issue must be logged
    sku_issues = [i for i in val["issues"] if "SKU formatting" in i["Problem"]]
    assert len(sku_issues) > 0

    # Cleaned dataframe must be trimmed uppercase
    clean_sales = val["cleaned_data"]["Sales_Lines"]
    assert clean_sales.loc[0, "SKU"] == "SKU1001"
    assert clean_sales.loc[1, "SKU"] == "SKU1002"


# ==============================================================================
# 4. DUPLICATE SALES HANDLING
# ==============================================================================
def test_04_duplicate_sales_handling():
    """Verify exact duplicate sales rows are detected, logged, and removed prior to analysis."""
    raw = load_workbook(SAMPLE_PATH)
    im, stock, sales, cust = [df.copy() for df in raw]

    val = validate_data(im, stock, sales, cust)
    assert val["duplicate_sales_rows"] == 6

    # Verify cleaned sales lines removed duplicates
    clean_sales = val["cleaned_data"]["Sales_Lines"]
    assert len(clean_sales) == len(sales) - 6
    assert clean_sales.duplicated().sum() == 0


# ==============================================================================
# 5. SWITCH CONSOLIDATION (RULE R3)
# ==============================================================================
def test_05_switch_consolidation():
    """
    Verify that Alternate Flag = SWITCH consolidates old SKU stock & sales under new SKU,
    and excludes the old SKU from analytical items.
    """
    im = pd.DataFrame([
        {
            "SKU": "OLD_SKU",
            "Item Name": "Old Product (10/case)",
            "Category": "Cat A",
            "Master Pack Qty": 10,
            "Unit Cost (Rs)": 50,
            "Alternate Item (name)": "New Product (10/case)",
            "Alternate Flag": "SWITCH",
            "Status": "Active",
        },
        {
            "SKU": "NEW_SKU",
            "Item Name": "New Product (10/case)",
            "Category": "Cat A",
            "Master Pack Qty": 10,
            "Unit Cost (Rs)": 50,
            "Alternate Item (name)": None,
            "Alternate Flag": None,
            "Status": "Active",
        },
    ])
    stock = pd.DataFrame([
        {"SKU": "OLD_SKU", "Qty 0-30 days": 10, "Qty 31-60 days": 0, "Qty 61-90 days": 0, "Qty 91-180 days": 20, "Qty 180+ days": 30},
        {"SKU": "NEW_SKU", "Qty 0-30 days": 5, "Qty 31-60 days": 0, "Qty 61-90 days": 0, "Qty 91-180 days": 15, "Qty 180+ days": 10},
    ])
    sales = pd.DataFrame([
        {"Month": "Apr-2026", "CustomerID": "C1", "CustomerName": "Cust 1", "Industry": "Cafe", "SKU": "OLD_SKU", "Qty": 40, "Value (Rs)": 2000},
        {"Month": "May-2026", "CustomerID": "C1", "CustomerName": "Cust 1", "Industry": "Cafe", "SKU": "NEW_SKU", "Qty": 60, "Value (Rs)": 3000},
    ])
    cust = pd.DataFrame([{"CustomerID": "C1", "CustomerName": "Cust 1", "Industry": "Cafe", "Area": "North"}])

    res = run_analysis(im, stock, sales, cust)
    items = res["analysis_items"]

    # OLD_SKU must not remain as a separate analytical item
    assert "OLD_SKU" not in items["SKU"].values
    assert "NEW_SKU" in items["SKU"].values

    new_row = items[items["SKU"] == "NEW_SKU"].iloc[0]
    # Total stock consolidated: (10 + 20 + 30) + (5 + 15 + 10) = 60 + 30 = 90
    assert new_row["Total Stock"] == 90
    # Aged Qty consolidated: (20 + 30) + (15 + 10) = 50 + 25 = 75
    assert new_row["Aged Qty"] == 75
    # 6M Sales consolidated: 40 + 60 = 100
    assert new_row["6M Sales Qty"] == 100


# ==============================================================================
# 6. INACTIVE ITEM EXCLUSION (RULE R4)
# ==============================================================================
def test_06_inactive_item_exclusion():
    """Verify items with Status = Inactive are excluded from active analysis items."""
    raw = load_workbook(SAMPLE_PATH)
    val = validate_data(*raw)
    res = run_analysis(*raw, validation=val)

    analysis_skus = res["analysis_items"]["SKU"].tolist()
    # SKU1041 is Inactive in sample Item_Master
    assert "SKU1041" not in analysis_skus
    assert len(res["analysis_items"]) == 38


# ==============================================================================
# 7. INACTIVE ITEM STOCK REPORTING (RULE R4)
# ==============================================================================
def test_07_inactive_item_stock_reporting():
    """Verify inactive items holding stock are separately reported and tracked."""
    raw = load_workbook(SAMPLE_PATH)
    val = validate_data(*raw)
    res = run_analysis(*raw, validation=val)

    inactive_stock = res["inactive_stock"]
    assert len(inactive_stock) == 1
    row = inactive_stock.iloc[0]
    assert row["SKU"] == "SKU1041"
    assert row["Total Stock"] == 169
    assert row["Total Stock Value"] == pytest.approx(14365.0)


# ==============================================================================
# 8. AGED QUANTITY CALCULATION (RULE R5)
# ==============================================================================
def test_08_aged_quantity_calculation():
    """Verify Aged Quantity = Qty 91-180 days + Qty 180+ days."""
    im = pd.DataFrame([{
        "SKU": "SKU_TEST", "Item Name": "Test Item", "Category": "Cat A",
        "Master Pack Qty": 10, "Unit Cost (Rs)": 20, "Alternate Item (name)": None,
        "Alternate Flag": None, "Status": "Active"
    }])
    stock = pd.DataFrame([{
        "SKU": "SKU_TEST",
        "Qty 0-30 days": 100,
        "Qty 31-60 days": 50,
        "Qty 61-90 days": 30,
        "Qty 91-180 days": 45,
        "Qty 180+ days": 65
    }])
    sales = pd.DataFrame([{
        "Month": "Apr-2026", "CustomerID": "C1", "CustomerName": "C1", "Industry": "Cafe",
        "SKU": "SKU_TEST", "Qty": 60, "Value (Rs)": 1200
    }])
    cust = pd.DataFrame([{"CustomerID": "C1", "CustomerName": "C1", "Industry": "Cafe", "Area": "North"}])

    res = run_analysis(im, stock, sales, cust)
    row = res["analysis_items"].iloc[0]
    assert row["Aged Qty"] == 45 + 65  # 110


# ==============================================================================
# 9. AGED VALUE CALCULATION (RULE R5)
# ==============================================================================
def test_09_aged_value_calculation():
    """Verify Aged Value = Aged Quantity × Unit Cost."""
    im = pd.DataFrame([{
        "SKU": "SKU_TEST", "Item Name": "Test Item", "Category": "Cat A",
        "Master Pack Qty": 10, "Unit Cost (Rs)": 25.0, "Alternate Item (name)": None,
        "Alternate Flag": None, "Status": "Active"
    }])
    stock = pd.DataFrame([{
        "SKU": "SKU_TEST",
        "Qty 0-30 days": 0, "Qty 31-60 days": 0, "Qty 61-90 days": 0,
        "Qty 91-180 days": 40, "Qty 180+ days": 60
    }])
    sales = pd.DataFrame([{
        "Month": "Apr-2026", "CustomerID": "C1", "CustomerName": "C1", "Industry": "Cafe",
        "SKU": "SKU_TEST", "Qty": 60, "Value (Rs)": 1500
    }])
    cust = pd.DataFrame([{"CustomerID": "C1", "CustomerName": "C1", "Industry": "Cafe", "Area": "North"}])

    res = run_analysis(im, stock, sales, cust)
    row = res["analysis_items"].iloc[0]
    assert row["Aged Qty"] == 100
    assert row["Aged Value"] == 100 * 25.0  # 2500.0


# ==============================================================================
# 10. AVERAGE MONTHLY SALES (RULE R5)
# ==============================================================================
def test_10_average_monthly_sales():
    """Verify Average Monthly Sales = 6-month sales quantity / 6."""
    im = pd.DataFrame([{
        "SKU": "SKU_TEST", "Item Name": "Test Item", "Category": "Cat A",
        "Master Pack Qty": 10, "Unit Cost (Rs)": 10, "Alternate Item (name)": None,
        "Alternate Flag": None, "Status": "Active"
    }])
    stock = pd.DataFrame([{
        "SKU": "SKU_TEST",
        "Qty 0-30 days": 50, "Qty 31-60 days": 0, "Qty 61-90 days": 0,
        "Qty 91-180 days": 0, "Qty 180+ days": 0
    }])
    sales = pd.DataFrame([{
        "Month": "Apr-2026", "CustomerID": "C1", "CustomerName": "C1", "Industry": "Cafe",
        "SKU": "SKU_TEST", "Qty": 90, "Value (Rs)": 900
    }])
    cust = pd.DataFrame([{"CustomerID": "C1", "CustomerName": "C1", "Industry": "Cafe", "Area": "North"}])

    res = run_analysis(im, stock, sales, cust)
    row = res["analysis_items"].iloc[0]
    assert row["6M Sales Qty"] == 90
    assert row["Avg Monthly Sales"] == pytest.approx(90 / 6.0)  # 15.0


# ==============================================================================
# 11. MONTHS TO CLEAR (RULE R5)
# ==============================================================================
def test_11_months_to_clear():
    """Verify Months to Clear = Total Stock / Average Monthly Sales."""
    im = pd.DataFrame([{
        "SKU": "SKU_TEST", "Item Name": "Test Item", "Category": "Cat A",
        "Master Pack Qty": 10, "Unit Cost (Rs)": 10, "Alternate Item (name)": None,
        "Alternate Flag": None, "Status": "Active"
    }])
    stock = pd.DataFrame([{
        "SKU": "SKU_TEST",
        "Qty 0-30 days": 60, "Qty 31-60 days": 0, "Qty 61-90 days": 0,
        "Qty 91-180 days": 0, "Qty 180+ days": 0
    }])
    sales = pd.DataFrame([{
        "Month": "Apr-2026", "CustomerID": "C1", "CustomerName": "C1", "Industry": "Cafe",
        "SKU": "SKU_TEST", "Qty": 120, "Value (Rs)": 1200
    }])
    cust = pd.DataFrame([{"CustomerID": "C1", "CustomerName": "C1", "Industry": "Cafe", "Area": "North"}])

    res = run_analysis(im, stock, sales, cust)
    row = res["analysis_items"].iloc[0]
    # Total Stock = 60, Avg Monthly Sales = 120/6 = 20 -> Months to Clear = 60 / 20 = 3.0
    assert row["Months to Clear"] == pytest.approx(3.0)


# ==============================================================================
# 12. RED LIST CLASSIFICATION (RULE R5 STEP 1)
# ==============================================================================
def test_12_red_list_classification():
    """Verify Rule R5 Step 1: Red List if 6-month sales quantity < 1 Master Pack."""
    im = pd.DataFrame([{
        "SKU": "SKU_RED", "Item Name": "Red Item", "Category": "Cat A",
        "Master Pack Qty": 50, "Unit Cost (Rs)": 10, "Alternate Item (name)": None,
        "Alternate Flag": None, "Status": "Active"
    }])
    stock = pd.DataFrame([{
        "SKU": "SKU_RED",
        "Qty 0-30 days": 10, "Qty 31-60 days": 0, "Qty 61-90 days": 0,
        "Qty 91-180 days": 0, "Qty 180+ days": 0
    }])
    # Sales = 49 units (< 50 Master Pack)
    sales = pd.DataFrame([{
        "Month": "Apr-2026", "CustomerID": "C1", "CustomerName": "C1", "Industry": "Cafe",
        "SKU": "SKU_RED", "Qty": 49, "Value (Rs)": 490
    }])
    cust = pd.DataFrame([{"CustomerID": "C1", "CustomerName": "C1", "Industry": "Cafe", "Area": "North"}])

    res = run_analysis(im, stock, sales, cust)
    assert res["analysis_items"].iloc[0]["Class"] == "Red List"


# ==============================================================================
# 13. NO ACTION CLASSIFICATION (RULE R5 STEP 2)
# ==============================================================================
def test_13_no_action_classification():
    """
    Verify Rule R5 Step 2: Otherwise No Action if Aged Quantity = 0 OR Months to Clear < 3.
    """
    im = pd.DataFrame([
        # Case A: Aged Qty == 0, but Months to Clear = 10 (>= 3) -> No Action
        {
            "SKU": "SKU_NOACT_A", "Item Name": "Item A", "Category": "Cat A",
            "Master Pack Qty": 10, "Unit Cost (Rs)": 10, "Alternate Item (name)": None,
            "Alternate Flag": None, "Status": "Active"
        },
        # Case B: Aged Qty = 20 (> 0), but Months to Clear = 2 (< 3) -> No Action
        {
            "SKU": "SKU_NOACT_B", "Item Name": "Item B", "Category": "Cat A",
            "Master Pack Qty": 10, "Unit Cost (Rs)": 10, "Alternate Item (name)": None,
            "Alternate Flag": None, "Status": "Active"
        },
    ])
    stock = pd.DataFrame([
        # Item A: Total Stock = 100, Aged Qty = 0
        {"SKU": "SKU_NOACT_A", "Qty 0-30 days": 100, "Qty 31-60 days": 0, "Qty 61-90 days": 0, "Qty 91-180 days": 0, "Qty 180+ days": 0},
        # Item B: Total Stock = 40, Aged Qty = 20
        {"SKU": "SKU_NOACT_B", "Qty 0-30 days": 20, "Qty 31-60 days": 0, "Qty 61-90 days": 0, "Qty 91-180 days": 10, "Qty 180+ days": 10},
    ])
    sales = pd.DataFrame([
        # Item A: 6M Sales = 60 (Avg Monthly = 10, Months to Clear = 10)
        {"Month": "Apr-2026", "CustomerID": "C1", "CustomerName": "C1", "Industry": "Cafe", "SKU": "SKU_NOACT_A", "Qty": 60, "Value (Rs)": 600},
        # Item B: 6M Sales = 120 (Avg Monthly = 20, Months to Clear = 40/20 = 2 < 3)
        {"Month": "Apr-2026", "CustomerID": "C1", "CustomerName": "C1", "Industry": "Cafe", "SKU": "SKU_NOACT_B", "Qty": 120, "Value (Rs)": 1200},
    ])
    cust = pd.DataFrame([{"CustomerID": "C1", "CustomerName": "C1", "Industry": "Cafe", "Area": "North"}])

    res = run_analysis(im, stock, sales, cust)
    items = res["analysis_items"].set_index("SKU")
    assert items.loc["SKU_NOACT_A", "Class"] == "No Action"
    assert items.loc["SKU_NOACT_B", "Class"] == "No Action"


# ==============================================================================
# 14. PUSH CLASSIFICATION (RULE R5 STEP 3)
# ==============================================================================
def test_14_push_classification():
    """Verify Rule R5 Step 3: Otherwise Push (Sales >= MP, Aged Qty > 0, Months to Clear >= 3)."""
    im = pd.DataFrame([{
        "SKU": "SKU_PUSH", "Item Name": "Push Item", "Category": "Cat A",
        "Master Pack Qty": 10, "Unit Cost (Rs)": 10, "Alternate Item (name)": None,
        "Alternate Flag": None, "Status": "Active"
    }])
    stock = pd.DataFrame([{
        "SKU": "SKU_PUSH",
        "Qty 0-30 days": 10, "Qty 31-60 days": 10, "Qty 61-90 days": 10,
        "Qty 91-180 days": 20, "Qty 180+ days": 20
    }])
    # Total stock = 70, Aged Qty = 40. Sales = 60 (Avg monthly = 10 -> Months to clear = 7 >= 3)
    sales = pd.DataFrame([{
        "Month": "Apr-2026", "CustomerID": "C1", "CustomerName": "C1", "Industry": "Cafe",
        "SKU": "SKU_PUSH", "Qty": 60, "Value (Rs)": 600
    }])
    cust = pd.DataFrame([{"CustomerID": "C1", "CustomerName": "C1", "Industry": "Cafe", "Area": "North"}])

    res = run_analysis(im, stock, sales, cust)
    assert res["analysis_items"].iloc[0]["Class"] == "Push"


# ==============================================================================
# 15. ZERO-SALES EDGE CASE
# ==============================================================================
def test_15_zero_sales_edge_case():
    """Verify zero sales quantity avoids division by zero, assigns Months to Clear = inf, and classifies as Red List."""
    im = pd.DataFrame([{
        "SKU": "SKU_ZERO", "Item Name": "Zero Sales Item", "Category": "Cat A",
        "Master Pack Qty": 10, "Unit Cost (Rs)": 10, "Alternate Item (name)": None,
        "Alternate Flag": None, "Status": "Active"
    }])
    stock = pd.DataFrame([{
        "SKU": "SKU_ZERO",
        "Qty 0-30 days": 50, "Qty 31-60 days": 0, "Qty 61-90 days": 0,
        "Qty 91-180 days": 0, "Qty 180+ days": 0
    }])
    # No sales rows for SKU_ZERO
    sales = pd.DataFrame(columns=["Month", "CustomerID", "CustomerName", "Industry", "SKU", "Qty", "Value (Rs)"])
    cust = pd.DataFrame([{"CustomerID": "C1", "CustomerName": "C1", "Industry": "Cafe", "Area": "North"}])

    res = run_analysis(im, stock, sales, cust)
    row = res["analysis_items"].iloc[0]
    assert row["6M Sales Qty"] == 0
    assert row["Avg Monthly Sales"] == 0
    assert row["Months to Clear"] == np.inf
    # 0 < 10 Master Pack -> Red List
    assert row["Class"] == "Red List"


# ==============================================================================
# 16. CUSTOMER ELIGIBILITY (> 100K SPEND)
# ==============================================================================
def test_16_customer_eligibility():
    """Verify Rule R6: Only customers with 6-month purchase value > ₹100,000 are eligible."""
    im = pd.DataFrame([{
        "SKU": "SKU_P", "Item Name": "Push Item", "Category": "Cat A",
        "Master Pack Qty": 10, "Unit Cost (Rs)": 10, "Alternate Item (name)": None,
        "Alternate Flag": None, "Status": "Active"
    }])
    stock = pd.DataFrame([{
        "SKU": "SKU_P",
        "Qty 0-30 days": 10, "Qty 31-60 days": 0, "Qty 61-90 days": 0,
        "Qty 91-180 days": 20, "Qty 180+ days": 20
    }])
    sales = pd.DataFrame([
        # Customer High: Spend = 100,001 (> 100k) -> Eligible
        {"Month": "Apr-2026", "CustomerID": "C_HIGH", "CustomerName": "High Spend", "Industry": "Cafe", "SKU": "SKU_P", "Qty": 20, "Value (Rs)": 100001},
        # Customer Exact: Spend = 100,000 (NOT > 100k) -> Ineligible
        {"Month": "Apr-2026", "CustomerID": "C_EXACT", "CustomerName": "Exact Spend", "Industry": "Cafe", "SKU": "SKU_P", "Qty": 20, "Value (Rs)": 100000},
        # Customer Low: Spend = 50,000 -> Ineligible
        {"Month": "Apr-2026", "CustomerID": "C_LOW", "CustomerName": "Low Spend", "Industry": "Cafe", "SKU": "SKU_P", "Qty": 20, "Value (Rs)": 50000},
    ])
    cust = pd.DataFrame([
        {"CustomerID": "C_HIGH", "CustomerName": "High Spend", "Industry": "Cafe", "Area": "North"},
        {"CustomerID": "C_EXACT", "CustomerName": "Exact Spend", "Industry": "Cafe", "Area": "North"},
        {"CustomerID": "C_LOW", "CustomerName": "Low Spend", "Industry": "Cafe", "Area": "North"},
    ])

    res = run_analysis(im, stock, sales, cust)
    targets = build_customer_targets(res["clean_item_master"], res["clean_sales"], res["analysis_items"], customers=cust)

    t = targets["SKU_P"]
    targeted_custs = t["CustomerID"].tolist()
    assert "C_HIGH" in targeted_custs
    assert "C_EXACT" not in targeted_custs
    assert "C_LOW" not in targeted_custs


# ==============================================================================
# 17. BUCKET 1 TARGETING (BOUGHT BEFORE)
# ==============================================================================
def test_17_bucket_1_targeting():
    """Verify Bucket 1: Eligible customers who previously bought the Push SKU or its switch partner."""
    raw = load_workbook(SAMPLE_PATH)
    val = validate_data(*raw)
    res = run_analysis(*raw, validation=val)
    targets = build_customer_targets(res["clean_item_master"], res["clean_sales"], res["analysis_items"], val, customers=raw[3])

    t = targets["SKU1005"]
    b1_custs = t[t["Bucket"] == 1]["CustomerID"].tolist()
    # Customer 220 and 224 previously bought SKU1005
    assert "C220" in b1_custs
    assert "C224" in b1_custs


# ==============================================================================
# 18. BUCKET 2 TARGETING (SIMILAR BUSINESS)
# ==============================================================================
def test_18_bucket_2_targeting():
    """
    Verify Bucket 2: Remaining eligible customers whose Industry matches an Industry
    associated with customers who previously bought the Push SKU.
    """
    raw = load_workbook(SAMPLE_PATH)
    val = validate_data(*raw)
    res = run_analysis(*raw, validation=val)
    targets = build_customer_targets(res["clean_item_master"], res["clean_sales"], res["analysis_items"], val, customers=raw[3])

    t = targets["SKU1005"]
    b2_custs = t[t["Bucket"] == 2]["CustomerID"].tolist()
    # Customer 214 is a Caterer (Caterer bought SKU1005 via C220)
    assert "C214" in b2_custs
    # C214 must not be in Bucket 1
    assert "C214" not in t[t["Bucket"] == 1]["CustomerID"].tolist()


# ==============================================================================
# 19. MISSING INDUSTRY EXCLUSION FROM BUCKET 2
# ==============================================================================
def test_19_missing_industry_exclusion_from_bucket_2():
    """Verify customers with missing Industry cannot enter Bucket 2."""
    raw = load_workbook(SAMPLE_PATH)
    val = validate_data(*raw)
    res = run_analysis(*raw, validation=val)
    targets = build_customer_targets(res["clean_item_master"], res["clean_sales"], res["analysis_items"], val, customers=raw[3])

    # Customer 217 has missing Industry in sample data
    for sku, df in targets.items():
        if df.empty:
            continue
        b2_custs = df[df["Bucket"] == 2]["CustomerID"].tolist()
        assert "C217" not in b2_custs, f"Customer C217 improperly entered Bucket 2 for {sku}!"


# ==============================================================================
# 20. BUCKET 3 TARGETING (SAME CATEGORY)
# ==============================================================================
def test_20_bucket_3_targeting():
    """Verify Bucket 3: Remaining eligible customers who bought another item in the same Category."""
    raw = load_workbook(SAMPLE_PATH)
    val = validate_data(*raw)
    res = run_analysis(*raw, validation=val)
    targets = build_customer_targets(res["clean_item_master"], res["clean_sales"], res["analysis_items"], val, customers=raw[3])

    t = targets["SKU1005"]
    b3_custs = t[t["Bucket"] == 3]["CustomerID"].tolist()
    # Hotel accounts (C221, C227) didn't buy SKU1005 or share Caterer/Restaurant industry,
    # but bought other Category A products
    assert "C221" in b3_custs
    assert "C227" in b3_custs


# ==============================================================================
# 21. BUCKET PRIORITY SORTING
# ==============================================================================
def test_21_bucket_priority_sorting():
    """Verify target lists are sorted by Bucket ascending, then 6M purchase value descending."""
    raw = load_workbook(SAMPLE_PATH)
    val = validate_data(*raw)
    res = run_analysis(*raw, validation=val)
    targets = build_customer_targets(res["clean_item_master"], res["clean_sales"], res["analysis_items"], val, customers=raw[3])

    for sku, df in targets.items():
        if df.empty:
            continue

        # Bucket must be non-decreasing
        buckets = df["Bucket"].tolist()
        assert buckets == sorted(buckets)

        # Within each bucket, 6M Purchase Value must be descending
        for b in [1, 2, 3]:
            sub = df[df["Bucket"] == b]
            if len(sub) > 1:
                vals = sub["6M Purchase Value"].tolist()
                assert vals == sorted(vals, reverse=True)


# ==============================================================================
# 22. NO DUPLICATE CUSTOMER ACROSS BUCKETS
# ==============================================================================
def test_22_no_duplicate_customer_across_buckets():
    """Verify strict mutual exclusivity: no customer appears in multiple buckets for the same SKU."""
    raw = load_workbook(SAMPLE_PATH)
    val = validate_data(*raw)
    res = run_analysis(*raw, validation=val)
    targets = build_customer_targets(res["clean_item_master"], res["clean_sales"], res["analysis_items"], val, customers=raw[3])

    for sku, df in targets.items():
        if df.empty:
            continue
        cids = df["CustomerID"].tolist()
        assert len(cids) == len(set(cids)), f"Duplicate customer detected in targets for {sku}!"


# ==============================================================================
# 23-26. CASE REGRESSION BENCHMARKS
# ==============================================================================
def test_23_regression_class_counts():
    """Regression test: Red List = 7, No Action = 13, Push = 18."""
    raw = load_workbook(SAMPLE_PATH)
    val = validate_data(*raw)
    res = run_analysis(*raw, validation=val)

    counts = res["analysis_items"]["Class"].value_counts().to_dict()
    assert counts.get("Red List", 0) == 7
    assert counts.get("No Action", 0) == 13
    assert counts.get("Push", 0) == 18


def test_24_regression_push_aged_value():
    """Regression test: Push Aged Value = ₹163,841."""
    raw = load_workbook(SAMPLE_PATH)
    val = validate_data(*raw)
    res = run_analysis(*raw, validation=val)

    items = res["analysis_items"]
    push_val = float(items.loc[items["Class"] == "Push", "Aged Value"].sum())
    assert push_val == 163841.0


def test_25_regression_specific_sku_classifications():
    """Regression test: SKU1001 = No Action, SKU1006 = Push, SKU1019 = Push, SKU1005 = Push."""
    raw = load_workbook(SAMPLE_PATH)
    val = validate_data(*raw)
    res = run_analysis(*raw, validation=val)

    classes = res["analysis_items"].set_index("SKU")["Class"].to_dict()
    assert classes["SKU1001"] == "No Action"
    assert classes["SKU1006"] == "Push"
    assert classes["SKU1019"] == "Push"
    assert classes["SKU1005"] == "Push"


def test_26_regression_sku1005_top_targets():
    """Regression test: SKU1005 top targets begin with Customer 220, Customer 224, and Customer 214."""
    raw = load_workbook(SAMPLE_PATH)
    val = validate_data(*raw)
    res = run_analysis(*raw, validation=val)
    targets = build_customer_targets(res["clean_item_master"], res["clean_sales"], res["analysis_items"], val, customers=raw[3])

    t = targets["SKU1005"]
    assert len(t) == 9
    assert t.iloc[0]["CustomerID"] == "C220" and t.iloc[0]["Bucket"] == 1
    assert t.iloc[1]["CustomerID"] == "C224" and t.iloc[1]["Bucket"] == 1
    assert t.iloc[2]["CustomerID"] == "C214" and t.iloc[2]["Bucket"] == 2
