"""
Automated unit and integration tests for the Four Separate Files upload interface
and schema-based file identification engine.

Covers user-specified test scenarios:
1. Test with four separate files.
2. Test selecting all four at once.
3. Test selecting only three files.
4. Test selecting five files.
5. Test wrong file.
6. Test duplicate/misidentified files.
7. Test valid four-file upload and end-to-end processing.
8. Confirm Combined Workbook mode still works.
9. Empty file (0 bytes) and invalid format handling.
"""

import io
import os
import pandas as pd
import pytest

from src.data_loader import (
    identify_uploaded_files,
    match_dataset_schema,
    load_data,
    load_separate_files,
    load_workbook,
    REQUIRED_SHEETS,
    REQUIRED_SCHEMAS,
)
from src.business_logic import run_analysis
from src.validation import validate_data


@pytest.fixture
def four_sample_files():
    """Generates four conformant Excel files as in-memory BytesIO buffers."""
    im_df = pd.DataFrame([
        {
            "SKU": "SKU_001",
            "Item Name": "Drill Bit",
            "Category": "Tools",
            "Master Pack Qty": 10,
            "Unit Cost (Rs)": 150.0,
            "Alternate Item (name)": None,
            "Alternate Flag": "N",
            "Status": "ACTIVE",
        }
    ])
    stock_df = pd.DataFrame([
        {
            "SKU": "SKU_001",
            "Qty 0-30 days": 100,
            "Qty 31-60 days": 20,
            "Qty 61-90 days": 10,
            "Qty 91-180 days": 50,
            "Qty 180+ days": 0,
        }
    ])
    sales_df = pd.DataFrame([
        {
            "Month": pd.Timestamp("2026-03-01"),
            "CustomerID": "CUST_01",
            "CustomerName": "Acme Builders",
            "Industry": "Construction",
            "SKU": "SKU_001",
            "Qty": 40,
            "Value (Rs)": 6000.0,
        }
    ])
    cust_df = pd.DataFrame([
        {
            "CustomerID": "CUST_01",
            "CustomerName": "Acme Builders",
            "Industry": "Construction",
            "Area": "North",
        }
    ])

    files = {}
    for name, df in [("Item_Master", im_df), ("Stock_Aging", stock_df), ("Sales_Lines", sales_df), ("Customers", cust_df)]:
        buf = io.BytesIO()
        df.to_excel(buf, index=False, sheet_name=name)
        buf.seek(0)
        buf.name = f"random_{name.lower()}_export.xlsx"  # Intentionally arbitrary filename
        files[name] = buf
    return files


@pytest.fixture
def combined_workbook_buf(four_sample_files):
    """Generates a single combined Excel workbook containing all 4 sheets."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for name, f in four_sample_files.items():
            f.seek(0)
            df = pd.read_excel(f)
            df.to_excel(writer, sheet_name=name, index=False)
            f.seek(0)
    buf.seek(0)
    buf.name = "Combined_CompanyX_Export.xlsx"
    return buf


def test_1_valid_four_separate_files_identification(four_sample_files):
    """
    TEST 1 & 2:
    Upload all four files simultaneously.
    Verify the application correctly matches each file to its dataset by column structure.
    """
    file_list = list(four_sample_files.values())
    res = identify_uploaded_files(file_list)

    assert res["all_identified"] is True
    assert len(res["errors"]) == 0
    assert len(res["missing_datasets"]) == 0
    assert len(res["duplicate_datasets"]) == 0
    assert len(res["unidentified_files"]) == 0

    for ds in REQUIRED_SHEETS:
        assert res["identified"][ds] is not None
        assert res[ds] is not None


def test_2_arbitrary_filenames_identified_by_content(four_sample_files):
    """
    Verify identification relies on column schema rather than filenames.
    """
    files = list(four_sample_files.values())
    files[0].name = "export_alpha.xlsx"
    files[1].name = "data_beta.xlsx"
    files[2].name = "report_gamma.xlsx"
    files[3].name = "table_delta.xlsx"

    res = identify_uploaded_files(files)
    assert res["all_identified"] is True
    assert res["identified"]["Item_Master"] is files[0]
    assert res["identified"]["Stock_Aging"] is files[1]
    assert res["identified"]["Sales_Lines"] is files[2]
    assert res["identified"]["Customers"] is files[3]


def test_3_selecting_only_three_files(four_sample_files):
    """
    TEST 3:
    Upload only 3 files.
    Verify application rejects execution, shows 'Please select all 4 required files',
    and identifies exactly which dataset is missing.
    """
    # Exclude Stock_Aging
    three_files = [four_sample_files["Item_Master"], four_sample_files["Sales_Lines"], four_sample_files["Customers"]]
    res = identify_uploaded_files(three_files)

    assert res["all_identified"] is False
    assert "Stock_Aging" in res["missing_datasets"]
    assert any("Please select all 4 required files" in e for e in res["errors"])


def test_4_selecting_five_files(four_sample_files):
    """
    TEST 4:
    Upload 5 files.
    Verify application shows error: 'Please select exactly 4 Excel files.'
    """
    five_files = list(four_sample_files.values()) + [four_sample_files["Item_Master"]]
    res = identify_uploaded_files(five_files)

    assert res["all_identified"] is False
    assert any("Please select exactly 4 Excel files" in e for e in res["errors"])


def test_5_wrong_file_unidentifiable_schema(four_sample_files):
    """
    TEST 5:
    Upload a file with unknown/unrelated columns.
    Verify file status is '⚠ Cannot identify' and error message is displayed.
    """
    wrong_buf = io.BytesIO()
    pd.DataFrame({"EmployeeID": [101, 102], "Salary": [50000, 60000]}).to_excel(wrong_buf, index=False)
    wrong_buf.seek(0)
    wrong_buf.name = "payroll_export.xlsx"

    files = [four_sample_files["Item_Master"], four_sample_files["Stock_Aging"], four_sample_files["Sales_Lines"], wrong_buf]
    res = identify_uploaded_files(files)

    assert res["all_identified"] is False
    assert "payroll_export.xlsx" in res["unidentified_files"]
    assert any("Unable to identify" in e for e in res["errors"])
    assert "Customers" in res["missing_datasets"]


def test_6_duplicate_dataset_matching(four_sample_files):
    """
    TEST 6:
    Upload two files matching the same schema (e.g. two Item_Master files).
    Verify application identifies duplicate and shows friendly error.
    """
    files = [
        four_sample_files["Item_Master"],
        four_sample_files["Item_Master"],
        four_sample_files["Stock_Aging"],
        four_sample_files["Sales_Lines"],
    ]
    res = identify_uploaded_files(files)

    assert res["all_identified"] is False
    assert "Item_Master" in res["duplicate_datasets"]
    assert any("Multiple files appear to match Item_Master" in e for e in res["errors"])
    assert "Customers" in res["missing_datasets"]


def test_7_valid_four_file_end_to_end_pipeline(four_sample_files):
    """
    TEST 7:
    Verify four identified files can be passed directly into load_data()
    and execute through the full validation and analysis pipeline.
    """
    file_list = list(four_sample_files.values())
    res = identify_uploaded_files(file_list)
    assert res["all_identified"] is True

    # Pass identified dict into load_data
    raw = load_data(res["identified"])
    assert len(raw) == 4
    im, stock, sales, cust = raw
    assert len(im) == 1
    assert len(stock) == 1
    assert len(sales) == 1
    assert len(cust) == 1

    val = validate_data(*raw)
    assert val["has_errors"] is False

    analysis = run_analysis(*raw, validation=val)
    assert "analysis_items" in analysis
    assert len(analysis["analysis_items"]) == 1


def test_8_combined_workbook_mode_still_works(combined_workbook_buf, four_sample_files):
    """
    TEST 8:
    Confirm Mode 1 (Combined Workbook) produces identical analytical results
    as Mode 2 (Four Separate Files).
    """
    raw_combined = load_data(combined_workbook_buf)
    raw_separate = load_data(list(four_sample_files.values()))

    val_combined = validate_data(*raw_combined)
    val_separate = validate_data(*raw_separate)

    res_combined = run_analysis(*raw_combined, validation=val_combined)
    res_separate = run_analysis(*raw_separate, validation=val_separate)

    items_comb = res_combined["analysis_items"]
    items_sep = res_separate["analysis_items"]

    assert items_comb.iloc[0]["Class"] == items_sep.iloc[0]["Class"]
    assert items_comb.iloc[0]["Total Stock"] == items_sep.iloc[0]["Total Stock"]
    assert items_comb.iloc[0]["Months to Clear"] == items_sep.iloc[0]["Months to Clear"]


def test_9_empty_and_corrupt_files_handled_gracefully(four_sample_files):
    """
    TEST 9:
    Empty file (0 bytes) or corrupted file must not raise unhandled exceptions.
    """
    empty_buf = io.BytesIO(b"")
    empty_buf.name = "empty_file.xlsx"

    files = [four_sample_files["Item_Master"], four_sample_files["Stock_Aging"], four_sample_files["Sales_Lines"], empty_buf]
    res = identify_uploaded_files(files)

    assert res["all_identified"] is False
    assert "empty_file.xlsx" in res["unidentified_files"]
    assert any("empty_file.xlsx" in e for e in res["errors"])
