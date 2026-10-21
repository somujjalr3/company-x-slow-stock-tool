"""
Enhanced Data Ingestion & Validation Automated Test Suite.

Covers all 18 validation requirements, 3 severity tiers (ERROR, WARNING, INFO),
structured result schema, and the Data Quality Score (0-100):
1. Missing required sheets (ERROR)
2. Missing required columns (ERROR)
3. Blank SKU (WARNING / ERROR)
4. Duplicate SKU in Item_Master (WARNING)
5. Invalid numeric values (WARNING)
6. Negative stock (WARNING)
7. Negative sales quantity (WARNING)
8. Negative unit cost (WARNING)
9. Invalid dates (WARNING)
10. Missing Customer ID (WARNING)
11. Missing Industry (WARNING)
12. Missing Category (WARNING)
13. Missing Master Pack (WARNING)
14. Invalid Master Pack values (WARNING)
15. Duplicate Sales_Lines records (INFO)
16. Invalid Alternate Flag (WARNING)
17. SWITCH records with missing new/partner SKU (WARNING)
18. Customers with missing purchase information (INFO)
19. Data Quality Score calculation (0-100)
20. Schema validation of structured issue fields
"""
import io
import pytest
import pandas as pd
import numpy as np

from src.data_loader import load_workbook, load_data, load_separate_files
from src.validation import validate_data, calculate_data_quality_score

SAMPLE_PATH = "sample_data/CompanyX_Data.xlsx"


@pytest.fixture
def clean_frames():
    raw = load_data(SAMPLE_PATH)
    return [df.copy() for df in raw]


# ==============================================================================
# 1. MISSING REQUIRED SHEETS (ERROR)
# ==============================================================================
def test_01_missing_required_sheets():
    buf = io.BytesIO()
    with pd.ExcelWriter(buf) as writer:
        pd.DataFrame({"SKU": ["SKU1"]}).to_excel(writer, sheet_name="Item_Master", index=False)
    buf.seek(0)

    # Ingestion fails with plain business language error
    with pytest.raises(ValueError, match="missing required sheet"):
        load_workbook(buf)

    # validate_data also catches None/missing DataFrame
    with pytest.raises(ValueError, match="is missing or not a valid DataFrame"):
        validate_data(pd.DataFrame(), None, pd.DataFrame(), pd.DataFrame(), raise_on_error=True)


# ==============================================================================
# 2. MISSING REQUIRED COLUMNS (ERROR)
# ==============================================================================
def test_02_missing_required_columns(clean_frames):
    im, stock, sales, cust = clean_frames
    im_bad = im.drop(columns=["Unit Cost (Rs)"])

    # raise_on_error=True raises ValueError
    with pytest.raises(ValueError, match="Unit Cost"):
        validate_data(im_bad, stock, sales, cust, raise_on_error=True)

    # raise_on_error=False records structured ERROR issue
    val = validate_data(im_bad, stock, sales, cust, raise_on_error=False)
    assert val["has_errors"] is True
    err_issues = [i for i in val["issues"] if i["Severity"] == "ERROR"]
    assert len(err_issues) >= 1
    assert any(i["Issue Type"] == "Missing Column" for i in err_issues)
    assert any("Unit Cost (Rs)" in i["Column"] for i in err_issues)


# ==============================================================================
# 3. BLANK SKU (WARNING / ERROR)
# ==============================================================================
def test_03_blank_sku(clean_frames):
    im, stock, sales, cust = clean_frames
    im.loc[0, "SKU"] = "   "  # Blank whitespace SKU
    sales.loc[0, "SKU"] = ""   # Empty string SKU

    val = validate_data(im, stock, sales, cust, raise_on_error=False)
    blank_issues = [i for i in val["issues"] if i["Issue Type"] == "Blank SKU"]
    assert len(blank_issues) >= 2
    sheets = [i["Sheet"] for i in blank_issues]
    assert "Item_Master" in sheets
    assert "Sales_Lines" in sheets
    for iss in blank_issues:
        assert iss["Severity"] in ["WARNING", "ERROR"]
        assert iss["Number of affected rows"] >= 1


# ==============================================================================
# 4. DUPLICATE SKU IN ITEM_MASTER (WARNING)
# ==============================================================================
def test_04_duplicate_sku_in_item_master(clean_frames):
    im, stock, sales, cust = clean_frames
    # Duplicate first row SKU
    dup_row = im.iloc[0:1].copy()
    im_dup = pd.concat([im, dup_row], ignore_index=True)

    val = validate_data(im_dup, stock, sales, cust, raise_on_error=False)
    dup_issues = [i for i in val["issues"] if i["Issue Type"] == "Duplicate SKU"]
    assert len(dup_issues) == 1
    iss = dup_issues[0]
    assert iss["Severity"] == "WARNING"
    assert iss["Sheet"] == "Item_Master"
    assert iss["Column"] == "SKU"
    assert iss["Number of affected rows"] == 1
    # Check deduplication in cleaned data
    assert len(val["cleaned_data"]["Item_Master"]) == len(im)


# ==============================================================================
# 5. INVALID NUMERIC VALUES (WARNING)
# ==============================================================================
def test_05_invalid_numeric_values(clean_frames):
    im, stock, sales, cust = clean_frames
    sales["Value (Rs)"] = sales["Value (Rs)"].astype(object)
    sales.loc[0, "Value (Rs)"] = "corrupt_text"

    val = validate_data(im, stock, sales, cust, raise_on_error=False)
    num_issues = [i for i in val["issues"] if i["Issue Type"] == "Invalid Numeric Values"]
    assert len(num_issues) >= 1
    assert any(i["Sheet"] == "Sales_Lines" and i["Column"] == "Value (Rs)" for i in num_issues)


# ==============================================================================
# 6. NEGATIVE STOCK (WARNING)
# ==============================================================================
def test_06_negative_stock(clean_frames):
    im, stock, sales, cust = clean_frames
    stock.loc[0, "Qty 91-180 days"] = -50

    val = validate_data(im, stock, sales, cust, raise_on_error=False)
    neg_issues = [i for i in val["issues"] if i["Issue Type"] == "Negative Stock Quantity"]
    assert len(neg_issues) >= 1
    assert any(i["Column"] == "Qty 91-180 days" for i in neg_issues)
    assert any("Replace invalid/negative" in i["How the application handled the issue"] for i in neg_issues)
    # Check that cleaned stock clips negative values
    assert (val["cleaned_data"]["Stock_Aging"]["Qty 91-180 days"] >= 0).all()


# ==============================================================================
# 7. NEGATIVE SALES QUANTITY (WARNING)
# ==============================================================================
def test_07_negative_sales_quantity(clean_frames):
    im, stock, sales, cust = clean_frames
    sales.loc[0, "Qty"] = -15  # Return / credit note

    val = validate_data(im, stock, sales, cust, raise_on_error=False)
    neg_sales = [i for i in val["issues"] if i["Issue Type"] == "Negative Sales Quantity"]
    assert len(neg_sales) >= 1
    iss = neg_sales[0]
    assert iss["Severity"] == "WARNING"
    assert iss["Sheet"] == "Sales_Lines"
    assert iss["Column"] == "Qty"
    assert iss["Number of affected rows"] >= 1


# ==============================================================================
# 8. NEGATIVE UNIT COST (WARNING)
# ==============================================================================
def test_08_negative_unit_cost(clean_frames):
    im, stock, sales, cust = clean_frames
    im.loc[0, "Unit Cost (Rs)"] = -120.0

    val = validate_data(im, stock, sales, cust, raise_on_error=False)
    neg_cost = [i for i in val["issues"] if i["Issue Type"] == "Negative Unit Cost"]
    assert len(neg_cost) >= 1
    iss = neg_cost[0]
    assert iss["Severity"] == "WARNING"
    assert iss["Sheet"] == "Item_Master"
    assert iss["Column"] == "Unit Cost (Rs)"


# ==============================================================================
# 9. INVALID DATES (WARNING)
# ==============================================================================
def test_09_invalid_dates(clean_frames):
    im, stock, sales, cust = clean_frames
    sales.loc[0, "Month"] = "UNPARSEABLE_DATE_999"

    val = validate_data(im, stock, sales, cust, raise_on_error=False)
    date_issues = [i for i in val["issues"] if i["Issue Type"] == "Invalid Date Values"]
    assert len(date_issues) == 1
    iss = date_issues[0]
    assert iss["Severity"] == "WARNING"
    assert iss["Sheet"] == "Sales_Lines"
    assert iss["Column"] == "Month"
    assert iss["Number of affected rows"] == 1


# ==============================================================================
# 10. MISSING CUSTOMER ID (WARNING)
# ==============================================================================
def test_10_missing_customer_id(clean_frames):
    im, stock, sales, cust = clean_frames
    cust.loc[0, "CustomerID"] = None

    val = validate_data(im, stock, sales, cust, raise_on_error=False)
    cust_issues = [i for i in val["issues"] if i["Issue Type"] == "Missing Customer ID"]
    assert len(cust_issues) >= 1
    assert any(i["Sheet"] == "Customers" for i in cust_issues)


# ==============================================================================
# 11. MISSING INDUSTRY (WARNING)
# ==============================================================================
def test_11_missing_industry(clean_frames):
    im, stock, sales, cust = clean_frames
    val = validate_data(im, stock, sales, cust, raise_on_error=False)
    ind_issues = [i for i in val["issues"] if i["Issue Type"] == "Missing Industry"]
    assert len(ind_issues) == 1
    iss = ind_issues[0]
    assert iss["Severity"] == "WARNING"
    assert iss["Sheet"] == "Customers"
    assert iss["Column"] == "Industry"
    assert iss["Number of affected rows"] == 1
    assert "Do not allow these customers into Bucket 2" in iss["How the application handled the issue"]


# ==============================================================================
# 12. MISSING CATEGORY (WARNING)
# ==============================================================================
def test_12_missing_category(clean_frames):
    im, stock, sales, cust = clean_frames
    im.loc[0, "Category"] = ""

    val = validate_data(im, stock, sales, cust, raise_on_error=False)
    cat_issues = [i for i in val["issues"] if i["Issue Type"] == "Missing Category"]
    assert len(cat_issues) == 1
    iss = cat_issues[0]
    assert iss["Severity"] == "WARNING"
    assert iss["Sheet"] == "Item_Master"
    assert iss["Column"] == "Category"


# ==============================================================================
# 13. MISSING MASTER PACK (WARNING)
# ==============================================================================
def test_13_missing_master_pack(clean_frames):
    im, stock, sales, cust = clean_frames
    im.loc[0, "Master Pack Qty"] = None

    val = validate_data(im, stock, sales, cust, raise_on_error=False)
    mp_issues = [i for i in val["issues"] if i["Issue Type"] == "Missing Master Pack"]
    assert len(mp_issues) == 1
    iss = mp_issues[0]
    assert iss["Severity"] == "WARNING"
    assert iss["Sheet"] == "Item_Master"
    assert iss["Column"] == "Master Pack Qty"


# ==============================================================================
# 14. INVALID MASTER PACK VALUES (WARNING)
# ==============================================================================
def test_14_invalid_master_pack_values(clean_frames):
    im, stock, sales, cust = clean_frames
    im.loc[0, "Master Pack Qty"] = -10  # Negative pack size

    val = validate_data(im, stock, sales, cust, raise_on_error=False)
    inv_mp = [i for i in val["issues"] if i["Issue Type"] == "Invalid Master Pack Values"]
    assert len(inv_mp) == 1
    iss = inv_mp[0]
    assert iss["Severity"] == "WARNING"
    assert iss["Sheet"] == "Item_Master"
    assert iss["Column"] == "Master Pack Qty"


# ==============================================================================
# 15. DUPLICATE SALES_LINES RECORDS (INFO)
# ==============================================================================
def test_15_duplicate_sales_lines_records(clean_frames):
    im, stock, sales, cust = clean_frames
    val = validate_data(im, stock, sales, cust, raise_on_error=False)
    dup_issues = [i for i in val["issues"] if i["Issue Type"] == "Duplicate Sales Records"]
    assert len(dup_issues) == 1
    iss = dup_issues[0]
    assert iss["Severity"] == "INFO"
    assert iss["Sheet"] == "Sales_Lines"
    assert iss["Number of affected rows"] == 6
    assert val["duplicate_sales_rows"] == 6


# ==============================================================================
# 16. INVALID ALTERNATE FLAG (WARNING)
# ==============================================================================
def test_16_invalid_alternate_flag(clean_frames):
    im, stock, sales, cust = clean_frames
    im.loc[0, "Alternate Flag"] = "UNRECOGNIZED_FLAG"

    val = validate_data(im, stock, sales, cust, raise_on_error=False)
    flag_issues = [i for i in val["issues"] if i["Issue Type"] == "Invalid Alternate Flag"]
    assert len(flag_issues) == 1
    iss = flag_issues[0]
    assert iss["Severity"] == "WARNING"
    assert iss["Sheet"] == "Item_Master"
    assert iss["Column"] == "Alternate Flag"


# ==============================================================================
# 17. SWITCH RECORDS WITH MISSING/UNRESOLVABLE PARTNER (WARNING)
# ==============================================================================
def test_17_switch_records_unresolvable_partner(clean_frames):
    im, stock, sales, cust = clean_frames
    im.loc[0, "Alternate Flag"] = "SWITCH"
    im.loc[0, "Alternate Item (name)"] = "NON_EXISTENT_PRODUCT_NAME_XYZ"

    val = validate_data(im, stock, sales, cust, raise_on_error=False)
    switch_issues = [i for i in val["issues"] if i["Issue Type"] == "Unresolved Switch Mapping"]
    assert len(switch_issues) == 1
    iss = switch_issues[0]
    assert iss["Severity"] == "WARNING"
    assert iss["Sheet"] == "Item_Master"
    assert iss["Column"] == "Alternate Item (name)"


# ==============================================================================
# 18. CUSTOMERS WITH MISSING PURCHASE INFORMATION (INFO)
# ==============================================================================
def test_18_customers_with_missing_purchase_information(clean_frames):
    im, stock, sales, cust = clean_frames
    val = validate_data(im, stock, sales, cust, raise_on_error=False)
    no_purchase = [i for i in val["issues"] if i["Issue Type"] == "Customer Without Purchases"]
    assert len(no_purchase) == 1
    iss = no_purchase[0]
    assert iss["Severity"] == "INFO"
    assert iss["Sheet"] == "Customers"
    assert iss["Column"] == "CustomerID"
    assert iss["Number of affected rows"] == 1  # C217


# ==============================================================================
# 19. DATA QUALITY SCORE (0-100)
# ==============================================================================
def test_19_data_quality_score_calculation(clean_frames):
    im, stock, sales, cust = clean_frames

    # Sample dataset has minor disclosures (score should be Grade A, 85-95)
    val = validate_data(im, stock, sales, cust, raise_on_error=False)
    score = val["data_quality_score"]
    assert 85 <= score <= 100
    assert val["summary"]["data_quality_score"] == score
    assert val["summary"]["errors"] == 0

    # Clean dataset with zero issues gets 100
    clean_score = calculate_data_quality_score([], {"Item_Master": im})
    assert clean_score == 100

    # Dataset with ERROR gets severely penalized
    err_issue = [{
        "Severity": "ERROR",
        "Number of affected rows": 10,
        "Sheet": "Item_Master",
    }]
    err_score = calculate_data_quality_score(err_issue, {"Item_Master": im})
    assert err_score <= 65


# ==============================================================================
# 20. STRUCTURED ISSUE SCHEMA COMPLETENESS
# ==============================================================================
def test_20_structured_validation_schema(clean_frames):
    val = validate_data(*clean_frames, raise_on_error=False)
    assert len(val["issues"]) > 0

    expected_keys = [
        "Severity",
        "Issue Type",
        "Sheet",
        "Column",
        "Number of affected rows",
        "Description",
        "How the application handled the issue",
        "Recommended source-level fix",
        # Backwards compatibility
        "Problem",
        "Count",
        "What the tool did",
    ]

    for iss in val["issues"]:
        for k in expected_keys:
            assert k in iss, f"Key '{k}' missing from structured issue: {iss}"
        assert iss["Severity"] in ["ERROR", "WARNING", "INFO"]
        assert isinstance(iss["Number of affected rows"], int)
        assert iss["Number of affected rows"] >= 0
