"""
Comprehensive test suite for application error handling, plain business language translation,
edge cases (zero sales, zero stock, no push items, no eligible customers), and developer diagnostics.
"""
import io
import os
import tempfile
import numpy as np
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
# 1. WRONG FILE TYPE
# ==============================================================================
def test_wrong_file_type_combined():
    """Verify that non-excel file extensions (.csv, .txt, .pdf, etc.) raise clear business error."""
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(b"a,b,c\n1,2,3\n")
        temp_csv = f.name

    try:
        with pytest.raises(ValueError) as excinfo:
            load_workbook(temp_csv)
        err = str(excinfo.value)
        assert "not a supported Excel workbook" in err
        assert ".csv" in err or temp_csv in err
    finally:
        os.remove(temp_csv)


def test_wrong_file_type_separate():
    """Verify that providing a non-excel file in separate upload mode raises clear business error."""
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        f.write(b"not an excel\n")
        temp_txt = f.name

    try:
        with pytest.raises(ValueError) as excinfo:
            load_separate_files(
                item_master_file=temp_txt,
                stock_aging_file=SAMPLE_PATH,
                sales_lines_file=SAMPLE_PATH,
                customers_file=SAMPLE_PATH,
            )
        err = str(excinfo.value)
        assert "not a supported Excel workbook" in err
    finally:
        os.remove(temp_txt)


# ==============================================================================
# 2. EMPTY FILE (0 BYTES)
# ==============================================================================
def test_empty_file_zero_bytes():
    """Verify that a 0-byte uploaded file raises an informative plain language error."""
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        temp_empty = f.name

    try:
        with pytest.raises(ValueError) as excinfo:
            load_workbook(temp_empty)
        err = str(excinfo.value)
        assert "empty (0 bytes)" in err
    finally:
        os.remove(temp_empty)


# ==============================================================================
# 3. CORRUPTED EXCEL FILE
# ==============================================================================
def test_corrupted_excel_file():
    """Verify that an invalid/corrupted binary file disguised as .xlsx raises plain business error."""
    buf = io.BytesIO(b"PK\x03\x04corrupted-excel-content-garbage-bytes")
    buf.name = "corrupted_monthly_export.xlsx"

    with pytest.raises(ValueError) as excinfo:
        load_workbook(buf)
    err = str(excinfo.value)
    assert "corrupted" in err.lower() or "cannot be read" in err.lower()


# ==============================================================================
# 4. MISSING WORKBOOK SHEETS
# ==============================================================================
def test_missing_workbook_sheets():
    """Verify missing required sheets in combined workbook produces plain business explanation."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf) as writer:
        pd.DataFrame({"SKU": ["SKU1"]}).to_excel(writer, sheet_name="Item_Master", index=False)
    buf.seek(0)
    buf.name = "partial_export.xlsx"

    with pytest.raises(ValueError) as excinfo:
        load_workbook(buf)
    err = str(excinfo.value)
    assert "missing required sheet(s)" in err
    assert "Stock_Aging" in err
    assert "Sales_Lines" in err
    assert "Customers" in err


# ==============================================================================
# 5. MISSING COLUMNS
# ==============================================================================
def test_missing_customer_id_column_plain_language():
    """
    Verify prompt example:
    Instead of: KeyError: 'CustomerID'
    Show: 'CustomerID is missing from Sales_Lines. Please upload the latest system export containing the required CustomerID column.'
    """
    raw = load_workbook(SAMPLE_PATH)
    im, stock, sales, cust = [df.copy() for df in raw]
    sales_no_cust = sales.drop(columns=["CustomerID"])

    with pytest.raises(ValueError) as excinfo:
        validate_data(im, stock, sales_no_cust, cust)
    err = str(excinfo.value)
    assert "CustomerID' is missing from Sales_Lines" in err
    assert "Please upload the latest system export containing the required CustomerID column" in err


def test_missing_sku_column_plain_language():
    """Verify missing SKU column produces plain business guidance."""
    raw = load_workbook(SAMPLE_PATH)
    im, stock, sales, cust = [df.copy() for df in raw]
    im_no_sku = im.drop(columns=["SKU"])

    with pytest.raises(ValueError) as excinfo:
        validate_data(im_no_sku, stock, sales, cust)
    err = str(excinfo.value)
    assert "SKU' is missing from Item_Master" in err
    assert "Please upload the latest system export" in err


# ==============================================================================
# 6. ERROR HANDLER TRANSLATION & DEVELOPER LOG
# ==============================================================================
def test_format_user_friendly_error_keyerror():
    """Verify format_user_friendly_error translates raw KeyError into plain business language."""
    # Simulate a raw KeyError: 'CustomerID'
    raw_exc = KeyError("CustomerID")
    friendly = format_user_friendly_error(raw_exc)

    assert "CustomerID is missing from Sales_Lines" in friendly["message"]
    assert "Please upload the latest system export containing the required CustomerID column." in friendly["message"]
    assert friendly["error_type"] == "KeyError"
    assert "KeyError" in friendly["traceback"]


def test_format_user_friendly_error_developer_traceback():
    """Verify that format_user_friendly_error preserves developer traceback for Developer Mode."""
    try:
        raise ValueError("Simulated unexpected pipeline failure")
    except Exception as exc:
        friendly = format_user_friendly_error(exc)

    assert friendly["error_type"] == "ValueError"
    assert "Simulated unexpected pipeline failure" in friendly["message"]
    assert "traceback" in friendly
    assert "test_format_user_friendly_error_developer_traceback" in friendly["traceback"]


# ==============================================================================
# 7. ZERO SALES EDGE CASE
# ==============================================================================
def test_zero_sales_edge_case_pipeline():
    """
    Verify complete pipeline handling when Sales_Lines contains 0 sales rows.
    All active items with positive master pack must be classified as Red List.
    No exceptions or division by zero should occur.
    """
    raw = load_workbook(SAMPLE_PATH)
    im, stock, sales, cust = [df.copy() for df in raw]
    empty_sales = sales.iloc[0:0].copy()

    val = validate_data(im, stock, empty_sales, cust)
    res = run_analysis(im, stock, empty_sales, cust, validation=val)
    targets = build_customer_targets(res["clean_item_master"], res["clean_sales"], res["analysis_items"], val, cust)
    audit = build_audit_trail([im, stock, empty_sales, cust], val, res, targets)

    items = res["analysis_items"]
    # All active catalog items with 6M sales < 1 Master Pack are Red List
    assert (items["6M Sales Qty"] == 0).all()
    assert (items["Class"] == "Red List").all()
    assert (items["Months to Clear"] == np.inf).all()
    assert len(targets) == 0  # No Push items exist

    # Excel export must also succeed cleanly
    excel_bytes = create_excel_report(items, targets, val, res["inactive_stock"], res["switch_map_df"])
    assert len(excel_bytes) > 0


# ==============================================================================
# 8. ZERO STOCK EDGE CASE
# ==============================================================================
def test_zero_stock_edge_case_pipeline():
    """
    Verify complete pipeline handling when warehouse holds 0 stock across all items.
    Items with sales >= 1 Master Pack should be classified as No Action.
    No division by zero or errors in KPI cards or export.
    """
    raw = load_workbook(SAMPLE_PATH)
    im, stock, sales, cust = [df.copy() for df in raw]
    stock_zero = stock.copy()
    stock_cols = ["Qty 0-30 days", "Qty 31-60 days", "Qty 61-90 days", "Qty 91-180 days", "Qty 180+ days"]
    for c in stock_cols:
        stock_zero[c] = 0

    val = validate_data(im, stock_zero, sales, cust)
    res = run_analysis(im, stock_zero, sales, cust, validation=val)
    targets = build_customer_targets(res["clean_item_master"], res["clean_sales"], res["analysis_items"], val, cust)

    items = res["analysis_items"]
    assert (items["Total Stock"] == 0).all()
    assert (items["Aged Qty"] == 0).all()
    assert (items["Aged Value"] == 0).all()
    # No Push items because Aged Qty == 0 -> No Action
    push_items = items[items["Class"] == "Push"]
    assert len(push_items) == 0

    excel_bytes = create_excel_report(items, targets, val, res["inactive_stock"], res["switch_map_df"])
    assert len(excel_bytes) > 0


# ==============================================================================
# 9. NO PUSH ITEMS EDGE CASE
# ==============================================================================
def test_no_push_items_reporting_and_export():
    """Verify that when 0 items qualify as Push, targeting and export handle it without error."""
    im = pd.DataFrame([{
        "SKU": "SKU_HEALTHY", "Item Name": "Fast Mover", "Category": "Cat A",
        "Master Pack Qty": 10, "Unit Cost (Rs)": 50, "Alternate Item (name)": None,
        "Alternate Flag": None, "Status": "Active"
    }])
    stock = pd.DataFrame([{
        "SKU": "SKU_HEALTHY",
        "Qty 0-30 days": 10, "Qty 31-60 days": 0, "Qty 61-90 days": 0,
        "Qty 91-180 days": 0, "Qty 180+ days": 0  # Aged Qty = 0 -> No Action
    }])
    sales = pd.DataFrame([{
        "Month": "Apr-2026", "CustomerID": "C1", "CustomerName": "Cust 1", "Industry": "Cafe",
        "SKU": "SKU_HEALTHY", "Qty": 60, "Value (Rs)": 3000
    }])
    cust = pd.DataFrame([{"CustomerID": "C1", "CustomerName": "Cust 1", "Industry": "Cafe", "Area": "North"}])

    res = run_analysis(im, stock, sales, cust)
    items = res["analysis_items"]
    assert (items["Class"] == "No Action").all()

    targets = build_customer_targets(res["clean_item_master"], res["clean_sales"], items, customers=cust)
    assert len(targets) == 0

    excel_bytes = create_excel_report(items, targets, {"issues": []}, res["inactive_stock"], res["switch_map_df"])
    assert len(excel_bytes) > 0


# ==============================================================================
# 10. NO ELIGIBLE CUSTOMERS EDGE CASE
# ==============================================================================
def test_no_eligible_customers_edge_case():
    """
    Verify that when Push items exist but no customers meet the > ₹100,000 spend threshold,
    the tool creates empty target DataFrames and generates the complete Excel report cleanly.
    """
    im = pd.DataFrame([{
        "SKU": "SKU_PUSH", "Item Name": "Slow Mover", "Category": "Cat A",
        "Master Pack Qty": 10, "Unit Cost (Rs)": 50, "Alternate Item (name)": None,
        "Alternate Flag": None, "Status": "Active"
    }])
    stock = pd.DataFrame([{
        "SKU": "SKU_PUSH",
        "Qty 0-30 days": 10, "Qty 31-60 days": 0, "Qty 61-90 days": 0,
        "Qty 91-180 days": 20, "Qty 180+ days": 20  # Total = 50, Aged = 40
    }])
    sales = pd.DataFrame([
        # All customer spends are strictly <= 100,000 -> Ineligible
        {"Month": "Apr-2026", "CustomerID": "C1", "CustomerName": "Cust 1", "Industry": "Cafe", "SKU": "SKU_PUSH", "Qty": 30, "Value (Rs)": 20000},
        {"Month": "May-2026", "CustomerID": "C2", "CustomerName": "Cust 2", "Industry": "Cafe", "SKU": "SKU_PUSH", "Qty": 30, "Value (Rs)": 50000},
    ])
    cust = pd.DataFrame([
        {"CustomerID": "C1", "CustomerName": "Cust 1", "Industry": "Cafe", "Area": "North"},
        {"CustomerID": "C2", "CustomerName": "Cust 2", "Industry": "Cafe", "Area": "North"},
    ])

    res = run_analysis(im, stock, sales, cust)
    items = res["analysis_items"]
    assert (items["Class"] == "Push").all()

    targets = build_customer_targets(res["clean_item_master"], res["clean_sales"], items, customers=cust)
    assert "SKU_PUSH" in targets
    assert targets["SKU_PUSH"].empty  # No customer > 100k spend

    excel_bytes = create_excel_report(items, targets, {"issues": []}, res["inactive_stock"], res["switch_map_df"])
    assert len(excel_bytes) > 0
