"""
Hardened Business Logic Rules (R1–R7) Test Suite.

Audits and proves:
R1: Dual input modes (combined workbook or 4 separate files).
R2: Validation and transparent problem handling.
R3: Alternate Flag = SWITCH consolidates old & new under new SKU; transitive chains.
R4: Inactive items excluded from main analysis; inactive items with stock reported separately.
R5: Inventory metrics and strict classification order:
    1. Red List if 6M Sales < 1 Master Pack
    2. No Action if Aged Qty = 0 OR Months to Clear < 3
    3. Push otherwise
R6: Customer targeting:
    - Eligible: 6M Purchase Value > 100,000
    - Bucket 1: Previous buyers of item or switch partner
    - Bucket 2: Remaining eligible with matching Industry (missing Industry barred)
    - Bucket 3: Remaining eligible who bought same Category
    - Mutual exclusivity across buckets
R7: Priority sorting:
    - Bucket ascending
    - 6M Purchase Value descending (deterministic tie-breaking)

Case Benchmarks:
- Red List = 7
- No Action = 13
- Push = 18
- Push Aged Value = 163,841
- SKU1001 = No Action
- SKU1006 = Push
- SKU1019 = Push
- SKU1005 = Push
- SKU1005 Targets: Customer 220 (B1) -> Customer 224 (B1) -> Customer 214 (B2)
"""
import io
import pytest
import pandas as pd
import numpy as np

from src.data_loader import load_workbook, load_separate_files, load_data
from src.validation import validate_data
from src.business_logic import run_analysis, build_switch_map
from src.customer_targets import build_customer_targets

SAMPLE_PATH = "sample_data/CompanyX_Data.xlsx"


# ==============================================================================
# RULE R1: DUAL INPUT MODES PARITY
# ==============================================================================
def test_r1_dual_input_modes_produce_identical_outputs():
    """R1: Input may be one combined workbook or four separate Excel files."""
    # Mode 1: Combined workbook
    raw_mode1 = load_workbook(SAMPLE_PATH)

    # Mode 2: Four separate Excel files
    im, stock, sales, cust = raw_mode1
    b_im = io.BytesIO(); im.to_excel(b_im, index=False, sheet_name="Item_Master"); b_im.seek(0)
    b_stock = io.BytesIO(); stock.to_excel(b_stock, index=False, sheet_name="Stock_Aging"); b_stock.seek(0)
    b_sales = io.BytesIO(); sales.to_excel(b_sales, index=False, sheet_name="Sales_Lines"); b_sales.seek(0)
    b_cust = io.BytesIO(); cust.to_excel(b_cust, index=False, sheet_name="Customers"); b_cust.seek(0)

    raw_mode2 = load_separate_files(b_im, b_stock, b_sales, b_cust)

    # Both modes load identical data
    assert len(raw_mode1) == 4
    assert len(raw_mode2) == 4
    for df1, df2 in zip(raw_mode1, raw_mode2):
        pd.testing.assert_frame_equal(df1, df2)

    # Both modes yield identical analysis results
    res1 = run_analysis(*raw_mode1)
    res2 = run_analysis(*raw_mode2)
    pd.testing.assert_frame_equal(res1["analysis_items"], res2["analysis_items"])
    pd.testing.assert_frame_equal(res1["inactive_stock"], res2["inactive_stock"])


# ==============================================================================
# RULE R2: VALIDATION AND TRANSPARENT PROBLEM REPORTING
# ==============================================================================
def test_r2_validation_reports_problems_and_handling():
    """R2: Validate data and clearly report problems and handling without silent deletion."""
    raw = load_workbook(SAMPLE_PATH)
    val = validate_data(*raw)

    issues = val["issues"]
    assert len(issues) > 0

    for iss in issues:
        assert "Severity" in iss
        assert "Issue Type" in iss
        assert "Sheet" in iss
        assert "Column" in iss
        assert "Number of affected rows" in iss
        assert "Description" in iss
        assert "How the application handled the issue" in iss
        assert "Recommended Source Fix" in iss

    # Raw data is preserved immutably
    assert "raw_data" in val
    assert len(val["raw_data"]["Sales_Lines"]) == len(raw[2])


# ==============================================================================
# RULE R3: PACK-SIZE SWITCH CONSOLIDATION
# ==============================================================================
def test_r3_switch_consolidation_under_new_sku():
    """R3: If Alternate Flag = SWITCH, consolidate old and new item under new SKU."""
    im = pd.DataFrame([
        {
            "SKU": "OLD_SKU", "Item Name": "Product Small (100ml)", "Category": "Beverages",
            "Master Pack Qty": 10, "Unit Cost (Rs)": 50, "Alternate Item (name)": "Product Large (200ml)",
            "Alternate Flag": "SWITCH", "Status": "Active"
        },
        {
            "SKU": "NEW_SKU", "Item Name": "Product Large (200ml)", "Category": "Beverages",
            "Master Pack Qty": 10, "Unit Cost (Rs)": 90, "Alternate Item (name)": None,
            "Alternate Flag": None, "Status": "Active"
        },
    ])
    stock = pd.DataFrame([
        {"SKU": "OLD_SKU", "Qty 0-30 days": 0, "Qty 31-60 days": 0, "Qty 61-90 days": 0, "Qty 91-180 days": 20, "Qty 180+ days": 10},
        {"SKU": "NEW_SKU", "Qty 0-30 days": 5, "Qty 31-60 days": 0, "Qty 61-90 days": 0, "Qty 91-180 days": 15, "Qty 180+ days": 5},
    ])
    sales = pd.DataFrame([
        {"Month": "Apr-2026", "CustomerID": "C1", "CustomerName": "Cust 1", "Industry": "Cafe", "SKU": "OLD_SKU", "Qty": 30, "Value (Rs)": 1500},
        {"Month": "Apr-2026", "CustomerID": "C2", "CustomerName": "Cust 2", "Industry": "Hotel", "SKU": "NEW_SKU", "Qty": 40, "Value (Rs)": 3600},
    ])
    cust = pd.DataFrame([
        {"CustomerID": "C1", "CustomerName": "Cust 1", "Industry": "Cafe", "Area": "North"},
        {"CustomerID": "C2", "CustomerName": "Cust 2", "Industry": "Hotel", "Area": "South"},
    ])

    res = run_analysis(im, stock, sales, cust)
    items = res["analysis_items"]

    # Old SKU must not remain as a separate analytical item
    assert "OLD_SKU" not in items["SKU"].values
    assert "NEW_SKU" in items["SKU"].values

    new_row = items[items["SKU"] == "NEW_SKU"].iloc[0]
    # Consolidated Sales: 30 (old) + 40 (new) = 70
    assert new_row["6M Sales Qty"] == 70
    # Consolidated Total Stock: (20+10) + (5+15+5) = 55
    assert new_row["Total Stock"] == 55
    # Consolidated Aged Qty: (20+10) + (15+5) = 50
    assert new_row["Aged Qty"] == 50


def test_r3_switch_strictly_requires_flag():
    """R3: Item name presence alone does NOT trigger switch unless Alternate Flag == 'SWITCH'."""
    im = pd.DataFrame([
        {
            "SKU": "SKU_A", "Item Name": "Product A", "Category": "Cat 1",
            "Master Pack Qty": 10, "Unit Cost (Rs)": 50, "Alternate Item (name)": "Product B",
            "Alternate Flag": None,  # NOT 'SWITCH'
            "Status": "Active"
        },
        {
            "SKU": "SKU_B", "Item Name": "Product B", "Category": "Cat 1",
            "Master Pack Qty": 10, "Unit Cost (Rs)": 50, "Alternate Item (name)": None,
            "Alternate Flag": None, "Status": "Active"
        },
    ])
    mapping, df = build_switch_map(im)
    assert len(mapping) == 0


def test_r3_transitive_switch_chain():
    """R3: Chained switches (A -> B -> C) resolve directly to canonical C."""
    im = pd.DataFrame([
        {"SKU": "A", "Item Name": "P1", "Alternate Item (name)": "P2", "Alternate Flag": "SWITCH", "Status": "Active"},
        {"SKU": "B", "Item Name": "P2", "Alternate Item (name)": "P3", "Alternate Flag": "SWITCH", "Status": "Active"},
        {"SKU": "C", "Item Name": "P3", "Alternate Item (name)": None, "Alternate Flag": None, "Status": "Active"},
    ])
    mapping, df = build_switch_map(im)
    assert mapping["A"] == "C"
    assert mapping["B"] == "C"


# ==============================================================================
# RULE R4: INACTIVE ITEMS EXCLUSION & SEPARATE REPORTING
# ==============================================================================
def test_r4_inactive_exclusion_and_separate_stock_reporting():
    """R4: Inactive items excluded from main analysis; inactive items with stock reported separately."""
    raw = load_workbook(SAMPLE_PATH)
    res = run_analysis(*raw)
    items = res["analysis_items"]
    inactive_stock = res["inactive_stock"]

    # Main analysis only contains Active items
    assert (items["Status"] == "Active").all()
    assert "SKU1041" not in items["SKU"].values

    # Inactive stock contains SKU1041 holding 169 units
    assert len(inactive_stock) == 1
    assert inactive_stock.iloc[0]["SKU"] == "SKU1041"
    assert inactive_stock.iloc[0]["Total Stock"] == 169
    assert inactive_stock.iloc[0]["Total Stock Value"] == pytest.approx(14365.0)


# ==============================================================================
# RULE R5: INVENTORY METRICS & CLASSIFICATION ORDER
# ==============================================================================
def test_r5_metric_formulas_exactness():
    """
    R5:
    Aged Qty = Qty 91-180 days + Qty 180+ days
    Aged Value = Aged Qty * Unit Cost
    Avg Monthly Sales = 6M Sales Qty / 6
    Months to Clear = Total Stock / Avg Monthly Sales
    """
    raw = load_workbook(SAMPLE_PATH)
    res = run_analysis(*raw)
    items = res["analysis_items"]

    for _, row in items.iterrows():
        exp_aged_qty = row["Qty 91-180 days"] + row["Qty 180+ days"]
        assert row["Aged Qty"] == exp_aged_qty

        exp_aged_val = exp_aged_qty * row["Unit Cost (Rs)"]
        assert row["Aged Value"] == pytest.approx(exp_aged_val)

        exp_avg_sales = row["6M Sales Qty"] / 6.0
        assert row["Avg Monthly Sales"] == pytest.approx(exp_avg_sales)

        if exp_avg_sales > 0:
            exp_mtc = row["Total Stock"] / exp_avg_sales
            assert row["Months to Clear"] == pytest.approx(exp_mtc)
        else:
            assert row["Months to Clear"] == float("inf")


def test_r5_strict_classification_order():
    """
    R5 Classification Order:
    1. RED LIST if 6M Sales Qty < 1 Master Pack
    2. Otherwise NO ACTION if Aged Qty = 0 OR Months to Clear < 3
    3. Otherwise PUSH
    """
    im = pd.DataFrame([
        # Item 1: Sales (5) < Master Pack (10) -> Must be RED LIST even though Aged Qty = 0
        {"SKU": "SKU_RED", "Item Name": "Item 1", "Category": "Cat", "Master Pack Qty": 10, "Unit Cost (Rs)": 100, "Alternate Item (name)": None, "Alternate Flag": None, "Status": "Active"},
        # Item 2: Sales (20) >= Master Pack (10), Aged Qty (0) == 0 -> NO ACTION
        {"SKU": "SKU_NA1", "Item Name": "Item 2", "Category": "Cat", "Master Pack Qty": 10, "Unit Cost (Rs)": 100, "Alternate Item (name)": None, "Alternate Flag": None, "Status": "Active"},
        # Item 3: Sales (60) >= Master Pack (10), Total Stock (15) / Avg Sales (10) = 1.5 < 3 -> NO ACTION
        {"SKU": "SKU_NA2", "Item Name": "Item 3", "Category": "Cat", "Master Pack Qty": 10, "Unit Cost (Rs)": 100, "Alternate Item (name)": None, "Alternate Flag": None, "Status": "Active"},
        # Item 4: Sales (60) >= Master Pack (10), Total Stock (50) / Avg Sales (10) = 5.0 >= 3 and Aged Qty > 0 -> PUSH
        {"SKU": "SKU_PUSH", "Item Name": "Item 4", "Category": "Cat", "Master Pack Qty": 10, "Unit Cost (Rs)": 100, "Alternate Item (name)": None, "Alternate Flag": None, "Status": "Active"},
    ])
    stock = pd.DataFrame([
        {"SKU": "SKU_RED", "Qty 0-30 days": 10, "Qty 31-60 days": 0, "Qty 61-90 days": 0, "Qty 91-180 days": 0, "Qty 180+ days": 0},
        {"SKU": "SKU_NA1", "Qty 0-30 days": 20, "Qty 31-60 days": 0, "Qty 61-90 days": 0, "Qty 91-180 days": 0, "Qty 180+ days": 0},
        {"SKU": "SKU_NA2", "Qty 0-30 days": 5, "Qty 31-60 days": 0, "Qty 61-90 days": 0, "Qty 91-180 days": 5, "Qty 180+ days": 5},
        {"SKU": "SKU_PUSH", "Qty 0-30 days": 10, "Qty 31-60 days": 0, "Qty 61-90 days": 0, "Qty 91-180 days": 20, "Qty 180+ days": 20},
    ])
    sales = pd.DataFrame([
        {"Month": "Apr-2026", "CustomerID": "C1", "CustomerName": "Cust 1", "Industry": "Cafe", "SKU": "SKU_RED", "Qty": 5, "Value (Rs)": 500},
        {"Month": "Apr-2026", "CustomerID": "C1", "CustomerName": "Cust 1", "Industry": "Cafe", "SKU": "SKU_NA1", "Qty": 20, "Value (Rs)": 2000},
        {"Month": "Apr-2026", "CustomerID": "C1", "CustomerName": "Cust 1", "Industry": "Cafe", "SKU": "SKU_NA2", "Qty": 60, "Value (Rs)": 6000},
        {"Month": "Apr-2026", "CustomerID": "C1", "CustomerName": "Cust 1", "Industry": "Cafe", "SKU": "SKU_PUSH", "Qty": 60, "Value (Rs)": 6000},
    ])
    cust = pd.DataFrame([{"CustomerID": "C1", "CustomerName": "Cust 1", "Industry": "Cafe", "Area": "North"}])

    res = run_analysis(im, stock, sales, cust)
    items = res["analysis_items"].set_index("SKU")["Class"].to_dict()

    assert items["SKU_RED"] == "Red List"
    assert items["SKU_NA1"] == "No Action"
    assert items["SKU_NA2"] == "No Action"
    assert items["SKU_PUSH"] == "Push"


# ==============================================================================
# RULE R6: CUSTOMER ELIGIBILITY & 3-TIER BUCKET ASSIGNMENT
# ==============================================================================
def test_r6_customer_spend_threshold_and_bucket_assignment():
    """
    R6:
    Eligible customers: 6M Purchase Value > 100,000.
    Bucket 1: Bought the item or switch partner.
    Bucket 2: Same Industry as a prior buyer of the item. Missing Industry cannot enter Bucket 2.
    Bucket 3: Bought another item in the same Category.
    No customer can appear in multiple buckets.
    """
    im = pd.DataFrame([
        {"SKU": "PUSH_SKU", "Item Name": "Product P", "Category": "Category A", "Master Pack Qty": 10, "Unit Cost (Rs)": 50, "Alternate Item (name)": None, "Alternate Flag": None, "Status": "Active"},
        {"SKU": "OTHER_SKU", "Item Name": "Product O", "Category": "Category A", "Master Pack Qty": 10, "Unit Cost (Rs)": 50, "Alternate Item (name)": None, "Alternate Flag": None, "Status": "Active"},
        {"SKU": "DIFF_CAT", "Item Name": "Product D", "Category": "Category B", "Master Pack Qty": 10, "Unit Cost (Rs)": 50, "Alternate Item (name)": None, "Alternate Flag": None, "Status": "Active"},
    ])
    stock = pd.DataFrame([
        {"SKU": "PUSH_SKU", "Qty 0-30 days": 10, "Qty 31-60 days": 0, "Qty 61-90 days": 0, "Qty 91-180 days": 25, "Qty 180+ days": 25},  # Total 60, Aged 50 -> Push
        {"SKU": "OTHER_SKU", "Qty 0-30 days": 10, "Qty 31-60 days": 0, "Qty 61-90 days": 0, "Qty 91-180 days": 0, "Qty 180+ days": 0},
        {"SKU": "DIFF_CAT", "Qty 0-30 days": 10, "Qty 31-60 days": 0, "Qty 61-90 days": 0, "Qty 91-180 days": 0, "Qty 180+ days": 0},
    ])
    sales = pd.DataFrame([
        # C1: bought PUSH_SKU, spend = 150k -> Bucket 1 (Industry: Cafe)
        {"Month": "Apr-2026", "CustomerID": "C1", "CustomerName": "Cust 1", "Industry": "Cafe", "SKU": "PUSH_SKU", "Qty": 30, "Value (Rs)": 150000},
        # C2: Industry Cafe (matches C1), bought OTHER_SKU, spend = 120k -> Bucket 2 (NOT Bucket 3)
        {"Month": "Apr-2026", "CustomerID": "C2", "CustomerName": "Cust 2", "Industry": "Cafe", "SKU": "OTHER_SKU", "Qty": 20, "Value (Rs)": 120000},
        # C3: Industry Hotel (no buyer of PUSH_SKU in Hotel), bought OTHER_SKU (Cat A), spend = 110k -> Bucket 3
        {"Month": "Apr-2026", "CustomerID": "C3", "CustomerName": "Cust 3", "Industry": "Hotel", "SKU": "OTHER_SKU", "Qty": 20, "Value (Rs)": 110000},
        # C4: Missing Industry, bought OTHER_SKU (Cat A), spend = 130k -> BARS from Bucket 2 -> Enters Bucket 3!
        {"Month": "Apr-2026", "CustomerID": "C4", "CustomerName": "Cust 4", "Industry": "", "SKU": "OTHER_SKU", "Qty": 20, "Value (Rs)": 130000},
        # C5: Ineligible customer (spend = 50k <= 100k) -> Must NOT appear in any bucket
        {"Month": "Apr-2026", "CustomerID": "C5", "CustomerName": "Cust 5", "Industry": "Cafe", "SKU": "PUSH_SKU", "Qty": 10, "Value (Rs)": 50000},
    ])
    cust = pd.DataFrame([
        {"CustomerID": "C1", "CustomerName": "Cust 1", "Industry": "Cafe", "Area": "North"},
        {"CustomerID": "C2", "CustomerName": "Cust 2", "Industry": "Cafe", "Area": "North"},
        {"CustomerID": "C3", "CustomerName": "Cust 3", "Industry": "Hotel", "Area": "South"},
        {"CustomerID": "C4", "CustomerName": "Cust 4", "Industry": None, "Area": "East"},  # Missing industry
        {"CustomerID": "C5", "CustomerName": "Cust 5", "Industry": "Cafe", "Area": "West"},  # Ineligible
    ])

    res = run_analysis(im, stock, sales, cust)
    targets = build_customer_targets(res["clean_item_master"], res["clean_sales"], res["analysis_items"], customers=cust)

    t_push = targets["PUSH_SKU"]
    assert len(t_push) == 4  # C1, C2, C3, C4 (C5 excluded)

    cust_buckets = t_push.set_index("CustomerID")["Bucket"].to_dict()
    assert cust_buckets["C1"] == 1  # Bought before
    assert cust_buckets["C2"] == 2  # Sector match (Cafe)
    assert cust_buckets["C3"] == 3  # Same category (Hotel)
    assert cust_buckets["C4"] == 3  # Missing industry barred from B2, placed in B3

    # Ineligible customer C5 strictly excluded
    assert "C5" not in cust_buckets

    # Mutual Exclusivity: Zero duplicates across buckets
    assert t_push["CustomerID"].duplicated().sum() == 0


# ==============================================================================
# RULE R7: TARGET SORTING ORDER
# ==============================================================================
def test_r7_sorting_by_bucket_asc_then_spend_desc():
    """R7: Sort customer targets by Bucket ascending, then 6M Purchase Value descending."""
    raw = load_workbook(SAMPLE_PATH)
    res = run_analysis(*raw)
    targets = build_customer_targets(
        res["clean_item_master"],
        res["clean_sales"],
        res["analysis_items"],
        customers=raw[3]
    )

    for sku, t_df in targets.items():
        if t_df.empty:
            continue

        # 1. Bucket must be non-decreasing
        buckets = t_df["Bucket"].tolist()
        assert buckets == sorted(buckets), f"Buckets not sorted ascending for {sku}: {buckets}"

        # 2. Within each bucket, 6M Purchase Value must be descending
        for b in [1, 2, 3]:
            b_df = t_df[t_df["Bucket"] == b]
            if len(b_df) > 1:
                spends = b_df["6M Purchase Value"].tolist()
                assert spends == sorted(spends, reverse=True), f"Spends not descending in Bucket {b} for {sku}: {spends}"

        # 3. Priority starts at 1 and increases monotonically
        assert t_df["Priority"].tolist() == list(range(1, len(t_df) + 1))


# ==============================================================================
# SAMPLE CASE REGRESSION BENCHMARKS VERIFICATION
# ==============================================================================
def test_sample_case_benchmarks_and_sku1005_top_targets():
    """
    Expected validation results using the supplied sample data:
    Red List = 7
    No Action = 13
    Push = 18
    Push Aged Value = ₹163,841

    SKU1001 = No Action
    SKU1006 = Push
    SKU1019 = Push
    SKU1005 = Push

    For SKU1005 the first three customer targets should be:
    1. Customer 220, Bucket 1
    2. Customer 224, Bucket 1
    3. Customer 214, Bucket 2
    """
    raw = load_workbook(SAMPLE_PATH)
    val = validate_data(*raw)
    res = run_analysis(*raw, validation=val)
    items = res["analysis_items"]

    counts = items["Class"].value_counts()
    assert int(counts.get("Red List", 0)) == 7
    assert int(counts.get("No Action", 0)) == 13
    assert int(counts.get("Push", 0)) == 18

    push_aged_value = float(items.loc[items["Class"] == "Push", "Aged Value"].sum())
    assert push_aged_value == pytest.approx(163841.0)

    # Specific SKU Checks
    sku_classes = items.set_index("SKU")["Class"].to_dict()
    assert sku_classes["SKU1001"] == "No Action"
    assert sku_classes["SKU1006"] == "Push"
    assert sku_classes["SKU1019"] == "Push"
    assert sku_classes["SKU1005"] == "Push"

    # SKU1005 Customer Targets
    targets = build_customer_targets(
        res["clean_item_master"],
        res["clean_sales"],
        items,
        val,
        customers=raw[3]
    )
    assert "SKU1005" in targets
    t_1005 = targets["SKU1005"]
    assert len(t_1005) >= 3

    top3 = t_1005.head(3)
    # Target 1: Customer 220, Bucket 1
    assert top3.iloc[0]["CustomerName"] == "Customer 220"
    assert top3.iloc[0]["Bucket"] == 1

    # Target 2: Customer 224, Bucket 1
    assert top3.iloc[1]["CustomerName"] == "Customer 224"
    assert top3.iloc[1]["Bucket"] == 1

    # Target 3: Customer 214, Bucket 2
    assert top3.iloc[2]["CustomerName"] == "Customer 214"
    assert top3.iloc[2]["Bucket"] == 2
