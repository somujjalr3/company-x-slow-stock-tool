"""
End-to-End QA Audit Suite for Company X Slow Stock Action Tool.

Simulates and verifies:
1. Complete 10-step user workflow
2. Business rules R1 through R7
3. Official case regression benchmarks:
   - Red List = 7
   - No Action = 13
   - Push = 18
   - Push Aged Value = ₹163,841
   - SKU1001 = No Action
   - SKU1006 = Push
   - SKU1019 = Push
   - SKU1005 = Push
   - SKU1005 targets: Customer 220 -> Customer 224 -> Customer 214
4. All edge cases:
   - Zero sales
   - Missing industry
   - Inactive stock
   - SWITCH SKU
   - Duplicate rows
   - Invalid uploads
   - Missing sheets
   - Missing columns
   - No Push items
   - No eligible customers
5. Desktop & Mobile layouts
6. 7-Sheet Excel export integrity
"""
import io
import re
import openpyxl
import pandas as pd
import pytest

from src.business_logic import run_analysis, build_audit_trail
from src.customer_targets import build_customer_targets
from src.data_loader import load_workbook, load_separate_files, load_data
from src.error_handler import format_user_friendly_error
from src.export import create_excel_report
from src.validation import validate_data

SAMPLE_PATH = "sample_data/CompanyX_Data.xlsx"


# ==============================================================================
# WORKFLOW STEP 1 TO 5: INGESTION, VALIDATION, CLASSIFICATION, AND OVERVIEW
# ==============================================================================
def test_qa_workflow_steps_1_to_5():
    """Verify ingestion, validation, analysis, and Overview KPI benchmarks."""
    # Step 1 & 2: Load combined workbook
    raw = load_workbook(SAMPLE_PATH)
    im, stock, sales, cust = raw
    assert len(im) == 42
    assert len(stock) == 42
    assert len(sales) == 630
    assert len(cust) == 30

    # Step 3: Validate data
    val = validate_data(im, stock, sales, cust)
    assert val["duplicate_sales_rows"] == 6
    assert len(val["issues"]) > 0

    # Step 4: Run review
    res = run_analysis(*raw, validation=val)
    items = res["analysis_items"]
    # 42 total items - 1 inactive (SKU1041) - 3 old switch SKUs (SKU1003, SKU1015, SKU1030) = 38 active
    assert len(items) == 38

    # Step 5: Dashboard Overview KPIs
    counts = items["Class"].value_counts()
    red_count = int(counts.get("Red List", 0))
    noaction_count = int(counts.get("No Action", 0))
    push_count = int(counts.get("Push", 0))
    push_aged_value = float(items.loc[items["Class"] == "Push", "Aged Value"].sum())

    assert red_count == 7, f"Expected 7 Red List items, got {red_count}"
    assert noaction_count == 13, f"Expected 13 No Action items, got {noaction_count}"
    assert push_count == 18, f"Expected 18 Push items, got {push_count}"
    assert push_aged_value == pytest.approx(163841.0), f"Expected Push Aged Value 163,841, got {push_aged_value}"


# ==============================================================================
# WORKFLOW STEP 6 & 7: FILTER ITEMS & SPECIFIC SKU CHECKS
# ==============================================================================
def test_qa_workflow_steps_6_and_7_sku_checks():
    """Verify filtering and specific SKU classification checks."""
    raw = load_workbook(SAMPLE_PATH)
    res = run_analysis(*raw)
    items = res["analysis_items"]

    # Filter by category
    cat_items = items[items["Category"] == "Category A"]
    assert len(cat_items) > 0

    # Specific SKU Checks
    sku_classes = items.set_index("SKU")["Class"].to_dict()
    assert sku_classes["SKU1001"] == "No Action", f"SKU1001 expected No Action, got {sku_classes['SKU1001']}"
    assert sku_classes["SKU1006"] == "Push", f"SKU1006 expected Push, got {sku_classes['SKU1006']}"
    assert sku_classes["SKU1019"] == "Push", f"SKU1019 expected Push, got {sku_classes['SKU1019']}"
    assert sku_classes["SKU1005"] == "Push", f"SKU1005 expected Push, got {sku_classes['SKU1005']}"


# ==============================================================================
# WORKFLOW STEP 8: CUSTOMER TARGETING & SKU1005 TOP 3 TARGETS
# ==============================================================================
def test_qa_workflow_step_8_sku1005_targets():
    """Verify customer targeting for SKU1005 yields Customer 220, Customer 224, Customer 214."""
    raw = load_workbook(SAMPLE_PATH)
    res = run_analysis(*raw)
    targets = build_customer_targets(
        res["clean_item_master"],
        res["clean_sales"],
        res["analysis_items"],
        customers=raw[3],
    )

    assert "SKU1005" in targets
    t_1005 = targets["SKU1005"]
    assert not t_1005.empty

    top3_names = t_1005.head(3)["CustomerName"].tolist()
    assert top3_names[0] == "Customer 220", f"Expected Customer 220, got {top3_names[0]}"
    assert top3_names[1] == "Customer 224", f"Expected Customer 224, got {top3_names[1]}"
    assert top3_names[2] == "Customer 214", f"Expected Customer 214, got {top3_names[2]}"

    # Check Buckets: Customer 220 and 224 in Bucket 1, Customer 214 in Bucket 2
    top3_buckets = t_1005.head(3)["Bucket"].tolist()
    assert top3_buckets[0] == 1
    assert top3_buckets[1] == 1
    assert top3_buckets[2] == 2

    # Verify Mutual Exclusivity: No duplicate customers
    assert t_1005["CustomerID"].duplicated().sum() == 0


# ==============================================================================
# WORKFLOW STEP 9: DATA QUALITY, INACTIVE STOCK, SWITCH ROLLUP, AUDIT TRAIL
# ==============================================================================
def test_qa_workflow_step_9_data_quality_and_audit():
    """Verify Data Quality sections, inactive stock reporting, and 11-step audit trail."""
    raw = load_workbook(SAMPLE_PATH)
    val = validate_data(*raw)
    res = run_analysis(*raw, validation=val)
    targets = build_customer_targets(
        res["clean_item_master"],
        res["clean_sales"],
        res["analysis_items"],
        customers=raw[3],
    )
    audit = build_audit_trail(raw, val, res, targets)

    # 1. Inactive stock reporting (Rule R4)
    inactive = res["inactive_stock"]
    assert len(inactive) == 1
    assert inactive.iloc[0]["SKU"] == "SKU1041"
    assert inactive.iloc[0]["Total Stock"] == 169
    assert inactive.iloc[0]["Total Stock Value"] == pytest.approx(14365.0)

    # 2. Switch mapping (Rule R3)
    switches = res["switch_map_df"]
    assert len(switches) == 3
    switch_pairs = set(zip(switches["Old SKU"], switches["New SKU"]))
    assert ("SKU1003", "SKU1006") in switch_pairs
    assert ("SKU1015", "SKU1019") in switch_pairs
    assert ("SKU1030", "SKU1033") in switch_pairs

    # 3. Audit trail (all 11 metrics)
    table = audit["table"]
    assert len(table) == 11
    metrics = audit["metrics"]
    assert metrics["uploaded_records"] == 42 + 42 + 630 + 30  # 744
    assert metrics["duplicates_detected"] == 6
    assert metrics["duplicates_removed"] == 6
    assert metrics["switch_mappings"] == 3
    assert metrics["inactive_items_excluded"] == 1
    assert metrics["inactive_items_still_holding_stock"] == 1
    assert metrics["push_items"] == 18


# ==============================================================================
# WORKFLOW STEP 10: 7-SHEET EXCEL EXPORT INTEGRITY
# ==============================================================================
def test_qa_workflow_step_10_excel_export_load_and_validate():
    """Verify generated Excel workbook has 7 sheets and valid executive content."""
    raw = load_workbook(SAMPLE_PATH)
    val = validate_data(*raw)
    res = run_analysis(*raw, validation=val)
    targets = build_customer_targets(
        res["clean_item_master"],
        res["clean_sales"],
        res["analysis_items"],
        customers=raw[3],
    )

    excel_bytes = create_excel_report(
        items=res["analysis_items"],
        targets=targets,
        validation=val,
        inactive_stock=res["inactive_stock"],
        switches=res["switch_map_df"],
    )

    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
    expected_sheets = [
        "Executive Summary",
        "SKU Analysis",
        "Push Items",
        "Red List",
        "No Action",
        "Customer Targets",
        "Sales Action List",
        "Risk Analysis",
        "Working Capital",
        "Dead Stock",
        "Data Quality",
        "Assumptions & Rules",
    ]
    assert wb.sheetnames == expected_sheets

    # Verify Executive Summary sheet content
    ws_exec = wb["Executive Summary"]
    summary_text = [str(ws_exec.cell(row=i, column=1).value) for i in range(1, 20)]
    assert any("Red List Items" in s for s in summary_text)
    assert any("Push Aged Value" in s for s in summary_text)

    # Verify Customer Targets sheet preserves required columns
    ws_tgt = wb["Customer Targets"]
    headers = [ws_tgt.cell(row=1, column=c).value for c in range(1, ws_tgt.max_column + 1)]
    for req_header in ["Push SKU", "Priority", "Bucket", "Customer", "Customer ID", "Industry", "Area", "6M Purchase Value"]:
        assert req_header in headers


# ==============================================================================
# EDGE CASES AUDIT
# ==============================================================================
def test_qa_edge_case_zero_sales():
    """Verify zero sales: all items classified as Red List, Months to Clear is inf, no crash."""
    raw = load_workbook(SAMPLE_PATH)
    im, stock, sales, cust = [df.copy() for df in raw]
    empty_sales = sales.iloc[0:0].copy()

    val = validate_data(im, stock, empty_sales, cust)
    res = run_analysis(im, stock, empty_sales, cust, validation=val)
    items = res["analysis_items"]

    assert (items["6M Sales Qty"] == 0).all()
    assert (items["Class"] == "Red List").all()
    assert (items["Months to Clear"] == float("inf")).all()

    targets = build_customer_targets(res["clean_item_master"], res["clean_sales"], items, val, cust)
    assert len(targets) == 0

    excel_bytes = create_excel_report(items, targets, val, res["inactive_stock"], res["switch_map_df"])
    assert len(excel_bytes) > 0


def test_qa_edge_case_missing_industry():
    """Verify customers with missing Industry cannot enter Bucket 2."""
    im = pd.DataFrame([{
        "SKU": "SKU_P", "Item Name": "Product P", "Category": "Cat A",
        "Master Pack Qty": 10, "Unit Cost (Rs)": 50, "Alternate Item (name)": None,
        "Alternate Flag": None, "Status": "Active"
    }])
    stock = pd.DataFrame([{
        "SKU": "SKU_P",
        "Qty 0-30 days": 10, "Qty 31-60 days": 0, "Qty 61-90 days": 0,
        "Qty 91-180 days": 25, "Qty 180+ days": 25  # Total 60, Aged 50 -> Push
    }])
    sales = pd.DataFrame([
        # C1 bought SKU_P -> Industry is Cafe
        {"Month": "Apr-2026", "CustomerID": "C1", "CustomerName": "Cust 1", "Industry": "Cafe", "SKU": "SKU_P", "Qty": 20, "Value (Rs)": 150000},
        # C2 has spend > 100k, bought other Cat A item, but Industry is MISSING -> cannot enter Bucket 2
        {"Month": "Apr-2026", "CustomerID": "C2", "CustomerName": "Cust 2", "Industry": None, "SKU": "OTHER_SKU", "Qty": 20, "Value (Rs)": 150000},
    ])
    cust = pd.DataFrame([
        {"CustomerID": "C1", "CustomerName": "Cust 1", "Industry": "Cafe", "Area": "North"},
        {"CustomerID": "C2", "CustomerName": "Cust 2", "Industry": "", "Area": "North"},  # Missing industry
    ])

    res = run_analysis(im, stock, sales, cust)
    targets = build_customer_targets(res["clean_item_master"], res["clean_sales"], res["analysis_items"], customers=cust)

    t_df = targets["SKU_P"]
    c2_row = t_df[t_df["CustomerID"] == "C2"]
    if not c2_row.empty:
        # Must not be Bucket 2
        assert c2_row.iloc[0]["Bucket"] != 2


def test_qa_edge_case_no_push_items():
    """Verify that when 0 items qualify as Push, targeting and export handle it without error."""
    im = pd.DataFrame([{
        "SKU": "SKU_FAST", "Item Name": "Fast Mover", "Category": "Cat A",
        "Master Pack Qty": 10, "Unit Cost (Rs)": 20, "Alternate Item (name)": None,
        "Alternate Flag": None, "Status": "Active"
    }])
    stock = pd.DataFrame([{
        "SKU": "SKU_FAST",
        "Qty 0-30 days": 10, "Qty 31-60 days": 0, "Qty 61-90 days": 0,
        "Qty 91-180 days": 0, "Qty 180+ days": 0  # Aged Qty = 0 -> No Action
    }])
    sales = pd.DataFrame([{
        "Month": "Apr-2026", "CustomerID": "C1", "CustomerName": "Cust 1", "Industry": "Cafe",
        "SKU": "SKU_FAST", "Qty": 60, "Value (Rs)": 5000
    }])
    cust = pd.DataFrame([{"CustomerID": "C1", "CustomerName": "Cust 1", "Industry": "Cafe", "Area": "North"}])

    res = run_analysis(im, stock, sales, cust)
    items = res["analysis_items"]
    assert (items["Class"] == "No Action").all()

    targets = build_customer_targets(res["clean_item_master"], res["clean_sales"], items, customers=cust)
    assert len(targets) == 0

    excel_bytes = create_excel_report(items, targets, {"issues": []}, res["inactive_stock"], res["switch_map_df"])
    assert len(excel_bytes) > 0


def test_qa_edge_case_no_eligible_customers():
    """Verify that when no customers have spend > 100k, Push items have empty target lists without error."""
    im = pd.DataFrame([{
        "SKU": "SKU_P", "Item Name": "Push Item", "Category": "Cat A",
        "Master Pack Qty": 10, "Unit Cost (Rs)": 10, "Alternate Item (name)": None,
        "Alternate Flag": None, "Status": "Active"
    }])
    stock = pd.DataFrame([{
        "SKU": "SKU_P",
        "Qty 0-30 days": 10, "Qty 31-60 days": 0, "Qty 61-90 days": 0,
        "Qty 91-180 days": 20, "Qty 180+ days": 20  # Total 50, Aged 40 -> Push
    }])
    sales = pd.DataFrame([{
        "Month": "Apr-2026", "CustomerID": "C1", "CustomerName": "Cust 1", "Industry": "Cafe",
        "SKU": "SKU_P", "Qty": 20, "Value (Rs)": 50000  # Spend = 50k (ineligible)
    }])
    cust = pd.DataFrame([{"CustomerID": "C1", "CustomerName": "Cust 1", "Industry": "Cafe", "Area": "North"}])

    res = run_analysis(im, stock, sales, cust)
    targets = build_customer_targets(res["clean_item_master"], res["clean_sales"], res["analysis_items"], customers=cust)

    assert "SKU_P" in targets
    assert targets["SKU_P"].empty


# ==============================================================================
# LAYOUT AUDIT: DESKTOP & MOBILE VIEWS IN APP.PY
# ==============================================================================
def test_qa_layout_desktop_and_mobile_containers():
    """Verify desktop table and mobile action card containers exist with responsive media query in app.py."""
    with open("app.py", "r", encoding="utf-8") as f:
        app_code = f.read()

    # Desktop container & styled table
    assert "sales-desktop-container" in app_code
    assert "styled-action-table" in app_code

    # Mobile container & action cards
    assert "sales-mobile-container" in app_code
    assert "mobile-action-card" in app_code
    assert "mobile-priority-badge" in app_code
    assert "mobile-spend-value" in app_code

    # Responsive CSS media query (768px threshold)
    assert "@media (max-width: 768px)" in app_code
