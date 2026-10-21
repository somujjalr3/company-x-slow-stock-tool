"""
Unit tests for the Data Quality audit layer and report structure.

Verifies:
- All 4 required fields are populated for every issue:
  1. Problem
  2. Number of affected records
  3. What the tool did
  4. Recommended source-level fix
- Separate categories exist:
  A. Formatting issues
  B. Duplicate records
  C. Missing master-data relationships
  D. Missing Industry
  E. Pack-size SWITCH mappings
  F. Inactive items with stock
- Auditor governance note is present
- No issues are silently dropped
"""
import pytest
from src.data_loader import load_data
from src.validation import validate_data
from src.business_logic import run_analysis

SAMPLE_PATH = "sample_data/CompanyX_Data.xlsx"


@pytest.fixture
def validated_data():
    raw = load_data(SAMPLE_PATH)
    val = validate_data(*raw)
    analysis = run_analysis(*raw, validation=val)
    return {
        "raw": raw,
        "validation": val,
        "analysis": analysis,
    }


def test_every_issue_contains_four_required_fields(validated_data):
    issues = validated_data["validation"]["issues"]
    assert len(issues) > 0

    required_fields = [
        "Problem",
        "Number of affected records",
        "What the tool did",
        "Recommended source-level fix"
    ]

    for iss in issues:
        for field in required_fields:
            assert field in iss, f"Field '{field}' missing from issue: {iss}"
            assert iss[field] is not None
            # Number of affected records must be a non-negative integer
            if field == "Number of affected records":
                assert isinstance(iss[field], int)
                assert iss[field] >= 0


def test_specific_sample_issues_and_four_fields(validated_data):
    issues = validated_data["validation"]["issues"]
    issue_by_problem = {iss["Problem"]: iss for iss in issues}

    # Issue 1: Stock_Aging invalid numeric
    assert "Invalid numeric values in Stock_Aging (Qty 31-60 days)" in issue_by_problem
    num_iss = issue_by_problem["Invalid numeric values in Stock_Aging (Qty 31-60 days)"]
    assert num_iss["Number of affected records"] == 1
    assert "Replace invalid/negative" in num_iss["What the tool did"]
    assert "Ensure Qty 31-60 days" in num_iss["Recommended source-level fix"]

    # Issue 2: Duplicate sales rows
    assert "Exact duplicate sales rows" in issue_by_problem
    dup_iss = issue_by_problem["Exact duplicate sales rows"]
    assert dup_iss["Number of affected records"] == 6
    assert "Remove exact duplicates" in dup_iss["What the tool did"]
    assert "unique transaction/line ID" in dup_iss["Recommended source-level fix"]

    # Issue 3: SKU formatting
    assert "SKU formatting inconsistencies in Sales_Lines" in issue_by_problem
    fmt_iss = issue_by_problem["SKU formatting inconsistencies in Sales_Lines"]
    assert fmt_iss["Number of affected records"] == 25
    assert "Trim whitespace" in fmt_iss["What the tool did"]
    assert "standardized SKU format" in fmt_iss["Recommended source-level fix"]

    # Issue 4: Missing industry
    assert "Customers with missing industry" in issue_by_problem
    ind_iss = issue_by_problem["Customers with missing industry"]
    assert ind_iss["Number of affected records"] == 1
    assert "Do not allow these customers into Bucket 2" in ind_iss["What the tool did"]
    assert "mandatory" in ind_iss["Recommended source-level fix"]


def test_sections_data_availability(validated_data):
    val = validated_data["validation"]
    analysis = validated_data["analysis"]

    # A. Formatting issues
    fmt_issues = [
        iss for iss in val["issues"]
        if "formatting" in iss["Problem"].lower() or "inconsistenc" in iss["Problem"].lower()
    ]
    assert len(fmt_issues) == 1
    assert fmt_issues[0]["Number of affected records"] == 25

    # B. Duplicate records
    dup_issues = [
        iss for iss in val["issues"]
        if "duplicate" in iss["Problem"].lower()
    ]
    assert len(dup_issues) == 1
    assert dup_issues[0]["Number of affected records"] == 6

    # C. Missing master relationships
    rel_issues = [
        iss for iss in val["issues"]
        if "not found in" in iss["Problem"].lower()
    ]
    # Sample file has 0 orphan records
    assert len(rel_issues) == 0

    # D. Missing Industry
    ind_issues = [
        iss for iss in val["issues"]
        if "industry" in iss["Problem"].lower()
    ]
    assert len(ind_issues) == 1
    assert ind_issues[0]["Number of affected records"] == 1

    # E. Pack-size SWITCH mappings (Rule R3)
    switches = analysis["switch_map_df"]
    assert len(switches) == 3

    # F. Inactive items with stock (Rule R4)
    inactive_stock = analysis["inactive_stock"]
    assert len(inactive_stock) == 1
    assert inactive_stock.iloc[0]["SKU"] == "SKU1041"
    assert inactive_stock.iloc[0]["Total Stock"] == 169
    assert inactive_stock.iloc[0]["Total Stock Value"] == pytest.approx(14365.0)


def test_governance_notice_in_app():
    with open("app.py", "r", encoding="utf-8") as f:
        content = f.read()

    expected_notice = "Data quality issues do not automatically mean the analysis is unusable. The tool applies defined handling rules and makes every material adjustment visible."
    assert expected_notice in content
