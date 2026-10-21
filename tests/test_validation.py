import io
import pytest
import pandas as pd
import numpy as np

from src.data_loader import load_workbook, load_separate_files, load_data, REQUIRED_SHEETS
from src.validation import validate_data, EXPECTED_COLUMNS
from src.business_logic import run_analysis
from src.customer_targets import build_customer_targets

SAMPLE_PATH = "sample_data/CompanyX_Data.xlsx"


def test_load_combined_workbook():
    raw = load_workbook(SAMPLE_PATH)
    assert len(raw) == 4
    im, stock, sales, cust = raw
    assert not im.empty
    assert not stock.empty
    assert not sales.empty
    assert not cust.empty
    assert len(im) == 42
    assert len(stock) == 42
    assert len(sales) == 630
    assert len(cust) == 30


def test_load_separate_files():
    # Split the sample workbook into 4 separate in-memory Excel files
    im = pd.read_excel(SAMPLE_PATH, sheet_name="Item_Master")
    stock = pd.read_excel(SAMPLE_PATH, sheet_name="Stock_Aging")
    sales = pd.read_excel(SAMPLE_PATH, sheet_name="Sales_Lines")
    cust = pd.read_excel(SAMPLE_PATH, sheet_name="Customers")

    b_im = io.BytesIO()
    im.to_excel(b_im, index=False, sheet_name="Sheet1")
    b_im.seek(0)

    b_stock = io.BytesIO()
    stock.to_excel(b_stock, index=False, sheet_name="Sheet1")
    b_stock.seek(0)

    b_sales = io.BytesIO()
    sales.to_excel(b_sales, index=False, sheet_name="Sheet1")
    b_sales.seek(0)

    b_cust = io.BytesIO()
    cust.to_excel(b_cust, index=False, sheet_name="Sheet1")
    b_cust.seek(0)

    # Load using load_separate_files with separate files
    loaded = load_separate_files(b_im, b_stock, b_sales, b_cust)
    assert len(loaded) == 4
    assert len(loaded[0]) == 42
    assert len(loaded[1]) == 42
    assert len(loaded[2]) == 630
    assert len(loaded[3]) == 30

    # Test load_data dispatcher with dict
    b_im.seek(0); b_stock.seek(0); b_sales.seek(0); b_cust.seek(0)
    loaded_dict = load_data({
        "Item_Master": b_im,
        "Stock_Aging": b_stock,
        "Sales_Lines": b_sales,
        "Customers": b_cust,
    })
    assert len(loaded_dict) == 4
    assert len(loaded_dict[0]) == 42


def test_missing_sheet_raises_error():
    buf = io.BytesIO()
    with pd.ExcelWriter(buf) as writer:
        pd.DataFrame({"a": [1]}).to_excel(writer, sheet_name="Item_Master", index=False)
    buf.seek(0)

    with pytest.raises(ValueError, match="missing required sheet"):
        load_workbook(buf)


def test_missing_column_raises_error():
    raw = load_workbook(SAMPLE_PATH)
    im, stock, sales, cust = [df.copy() for df in raw]
    im_bad = im.drop(columns=["Master Pack Qty"])

    with pytest.raises(ValueError, match="Item_Master is missing columns"):
        validate_data(im_bad, stock, sales, cust)


def test_empty_sheet_detection():
    raw = load_workbook(SAMPLE_PATH)
    im, stock, sales, cust = [df.copy() for df in raw]
    sales_empty = sales.iloc[0:0]

    val = validate_data(im, stock, sales_empty, cust)
    problems = [i["Problem"] for i in val["issues"]]
    assert "Sales_Lines is empty" in problems


def test_missing_values_in_important_fields():
    raw = load_workbook(SAMPLE_PATH)
    im, stock, sales, cust = [df.copy() for df in raw]
    im.loc[0, "Item Name"] = ""
    sales.loc[0, "Month"] = np.nan

    val = validate_data(im, stock, sales, cust)
    problems = [i["Problem"] for i in val["issues"]]
    assert any("Missing values in Item_Master (Item Name)" in p for p in problems)
    assert any("Missing values in Sales_Lines (Month)" in p for p in problems)


def test_invalid_numeric_values():
    raw = load_workbook(SAMPLE_PATH)
    im, stock, sales, cust = [df.copy() for df in raw]
    im.loc[0, "Master Pack Qty"] = -5
    im.loc[1, "Unit Cost (Rs)"] = 0
    stock.loc[0, "Qty 0-30 days"] = -10
    sales.loc[0, "Qty"] = -1
    sales.loc[1, "Value (Rs)"] = 0

    val = validate_data(im, stock, sales, cust)
    problems = [i["Problem"] for i in val["issues"]]
    assert any("Invalid numeric values in Item_Master (Master Pack Qty)" in p for p in problems)
    assert any("Invalid numeric values in Item_Master (Unit Cost (Rs))" in p for p in problems)
    assert any("Invalid numeric values in Stock_Aging (Qty 0-30 days)" in p for p in problems)
    assert any("Invalid numeric values in Sales_Lines (Qty)" in p for p in problems)
    assert any("Invalid numeric values in Sales_Lines (Value (Rs))" in p for p in problems)


def test_duplicate_sales_rows():
    raw = load_workbook(SAMPLE_PATH)
    im, stock, sales, cust = [df.copy() for df in raw]
    val = validate_data(im, stock, sales, cust)
    dup_issues = [i for i in val["issues"] if i["Problem"] == "Exact duplicate sales rows"]
    assert len(dup_issues) == 1
    assert dup_issues[0]["Count"] == 6


def test_inconsistent_sku_and_customer_formatting():
    raw = load_workbook(SAMPLE_PATH)
    im, stock, sales, cust = [df.copy() for df in raw]
    sales.loc[0, "CustomerID"] = " c201 "

    val = validate_data(im, stock, sales, cust)
    problems = [i["Problem"] for i in val["issues"]]
    assert "SKU formatting inconsistencies in Sales_Lines" in problems
    assert "CustomerID formatting inconsistencies in Sales_Lines" in problems


def test_orphan_skus_and_customers():
    raw = load_workbook(SAMPLE_PATH)
    im, stock, sales, cust = [df.copy() for df in raw]
    sales.loc[0, "SKU"] = "SKU9999"
    sales.loc[0, "CustomerID"] = "C999"

    val = validate_data(im, stock, sales, cust)
    problems = [i["Problem"] for i in val["issues"]]
    assert "Sales SKUs not found in item master" in problems
    assert "Sales customer IDs not found in customer master" in problems


def test_customers_with_missing_industry():
    raw = load_workbook(SAMPLE_PATH)
    im, stock, sales, cust = [df.copy() for df in raw]
    val = validate_data(im, stock, sales, cust)
    missing_ind = [i for i in val["issues"] if i["Problem"] == "Customers with missing industry"]
    assert len(missing_ind) == 1
    assert missing_ind[0]["Count"] == 1


def test_invalid_alternate_flag_and_status():
    raw = load_workbook(SAMPLE_PATH)
    im, stock, sales, cust = [df.copy() for df in raw]
    im.loc[0, "Alternate Flag"] = "INVALID_FLAG"
    im.loc[0, "Status"] = "ARCHIVED"

    val = validate_data(im, stock, sales, cust)
    problems = [i["Problem"] for i in val["issues"]]
    assert "Invalid or unrecognised Alternate Flag values in Item_Master" in problems
    assert "Invalid or missing Status values in Item_Master" in problems


def test_sample_workbook_clean_run_and_expected_outputs():
    raw = load_workbook(SAMPLE_PATH)
    val = validate_data(*raw)

    # Verify structured issues
    for issue in val["issues"]:
        assert "Severity" in issue
        assert "Issue Type" in issue
        assert "Sheet" in issue
        assert "Column" in issue
        assert "Number of affected rows" in issue
        assert "Description" in issue
        assert "How the application handled the issue" in issue
        assert "Problem" in issue
        assert "Count" in issue
        assert "Tool Handling" in issue
        assert "Recommended Source Fix" in issue

    # Verify expected issues count on sample file (4 data hygiene + 1 zero-purchase account disclosure)
    assert len(val["issues"]) == 5
    issue_map = {i["Problem"]: i["Count"] for i in val["issues"]}
    assert issue_map["Invalid numeric values in Stock_Aging (Qty 31-60 days)"] == 1
    assert issue_map["Exact duplicate sales rows"] == 6
    assert issue_map["SKU formatting inconsistencies in Sales_Lines"] == 25
    assert issue_map["Customers with missing industry"] == 1
    assert issue_map["Customer master accounts with zero recorded purchases"] == 1

    # Verify Data Quality Score (0-100)
    assert "data_quality_score" in val
    assert 85 <= val["data_quality_score"] <= 100

    # Verify business logic outputs match expected case benchmarks
    analysis = run_analysis(*raw, validation=val)
    items = analysis["analysis_items"]
    counts = items["Class"].value_counts().to_dict()

    assert counts.get("Red List", 0) == 7
    assert counts.get("No Action", 0) == 13
    assert counts.get("Push", 0) == 18

    push_val = float(items.loc[items["Class"] == "Push", "Aged Value"].sum())
    assert push_val == 163841.0

    sku_classes = items.set_index("SKU")["Class"].to_dict()
    assert sku_classes["SKU1001"] == "No Action"
    assert sku_classes["SKU1006"] == "Push"
    assert sku_classes["SKU1019"] == "Push"
    assert sku_classes["SKU1005"] == "Push"

    # Customer targeting
    targets = build_customer_targets(
        analysis["clean_item_master"],
        analysis["clean_sales"],
        items,
        val,
        customers=raw[3]
    )
    t_1005 = targets["SKU1005"]
    assert t_1005.iloc[0]["CustomerID"] == "C220"
    assert t_1005.iloc[0]["Bucket"] == 1
    assert t_1005.iloc[1]["CustomerID"] == "C224"
    assert t_1005.iloc[1]["Bucket"] == 1
    assert t_1005.iloc[2]["CustomerID"] == "C214"
    assert t_1005.iloc[2]["Bucket"] == 2


def test_both_modes_produce_identical_dataframe_structure_and_results():
    """Verify Requirement 4, 5, 9, 10:
    Both upload modes produce identical internal DataFrames,
    use the same validation and business logic, and yield identical case results.
    """
    # Mode 1: Combined workbook
    raw_mode1 = load_workbook(SAMPLE_PATH)

    # Mode 2: Four separate Excel files
    im, stock, sales, cust = raw_mode1
    b_im = io.BytesIO(); im.to_excel(b_im, index=False, sheet_name="Item_Master"); b_im.seek(0)
    b_stock = io.BytesIO(); stock.to_excel(b_stock, index=False, sheet_name="Stock_Aging"); b_stock.seek(0)
    b_sales = io.BytesIO(); sales.to_excel(b_sales, index=False, sheet_name="Sales_Lines"); b_sales.seek(0)
    b_cust = io.BytesIO(); cust.to_excel(b_cust, index=False, sheet_name="Customers"); b_cust.seek(0)

    raw_mode2 = load_separate_files(b_im, b_stock, b_sales, b_cust)

    # 4. Exactly the same internal DataFrame structure
    assert len(raw_mode1) == len(raw_mode2)
    for df1, df2 in zip(raw_mode1, raw_mode2):
        pd.testing.assert_frame_equal(df1, df2)

    # 5. Same validation engine
    val1 = validate_data(*raw_mode1)
    val2 = validate_data(*raw_mode2)
    assert val1["issues"] == val2["issues"]

    # 6. Same business-logic engine
    analysis1 = run_analysis(*raw_mode1, validation=val1)
    analysis2 = run_analysis(*raw_mode2, validation=val2)
    pd.testing.assert_frame_equal(analysis1["analysis_items"], analysis2["analysis_items"])
    pd.testing.assert_frame_equal(analysis1["inactive_stock"], analysis2["inactive_stock"])

    targets1 = build_customer_targets(analysis1["clean_item_master"], analysis1["clean_sales"], analysis1["analysis_items"], val1, customers=raw_mode1[3])
    targets2 = build_customer_targets(analysis2["clean_item_master"], analysis2["clean_sales"], analysis2["analysis_items"], val2, customers=raw_mode2[3])

    assert set(targets1.keys()) == set(targets2.keys())
    for sku in targets1:
        pd.testing.assert_frame_equal(targets1[sku], targets2[sku])


def test_separate_files_missing_file_plain_language_error():
    """Verify Requirement 2 & 8: Ambiguous uploads prevented and clear plain-language error given."""
    buf = io.BytesIO()
    with pytest.raises(ValueError, match="Incomplete upload: Missing file"):
        load_separate_files(item_master_file=buf, stock_aging_file=buf, sales_lines_file=buf, customers_file=None)

