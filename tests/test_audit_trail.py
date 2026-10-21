"""
Unit tests for the Analysis Audit trail (build_audit_trail).

Verifies the 11 audit indicators required for management and case evaluation:
1. Number of uploaded records
2. Number of exact duplicates detected
3. Number of duplicates removed
4. Number of SKU formatting corrections
5. Number of customer ID formatting corrections
6. Number of SWITCH mappings
7. Number of inactive items excluded
8. Number of inactive items still holding stock
9. Number of eligible customers
10. Number of Push items
11. Number of customer targets generated
"""
import pytest
from src.data_loader import load_data
from src.validation import validate_data
from src.business_logic import run_analysis, build_audit_trail
from src.customer_targets import build_customer_targets

SAMPLE_PATH = "sample_data/CompanyX_Data.xlsx"


@pytest.fixture
def sample_pipeline_output():
    raw = load_data(SAMPLE_PATH)
    val = validate_data(*raw)
    analysis = run_analysis(*raw, validation=val)
    targets = build_customer_targets(
        analysis["clean_item_master"],
        analysis["clean_sales"],
        analysis["analysis_items"],
        val,
        customers=raw[3]
    )
    return raw, val, analysis, targets


def test_build_audit_trail_all_11_metrics(sample_pipeline_output):
    raw, val, analysis, targets = sample_pipeline_output
    audit = build_audit_trail(raw, val, analysis, targets)

    assert "metrics" in audit
    assert "table" in audit

    m = audit["metrics"]

    # 1. Number of uploaded records (42 + 42 + 630 + 30 = 744)
    assert m["uploaded_records"] == 744

    # 2. Number of exact duplicates detected
    assert m["duplicates_detected"] == 6

    # 3. Number of duplicates removed
    assert m["duplicates_removed"] == 6

    # 4. Number of SKU formatting corrections (trimmed / uppercased in Sales_Lines)
    assert m["sku_formatting_corrections"] == 25

    # 5. Number of customer ID formatting corrections
    assert m["customer_id_formatting_corrections"] == 0

    # 6. Number of SWITCH mappings
    assert m["switch_mappings"] == 3

    # 7. Number of inactive items excluded
    assert m["inactive_items_excluded"] == 1

    # 8. Number of inactive items still holding stock (SKU1041)
    assert m["inactive_items_still_holding_stock"] == 1

    # 9. Number of eligible customers (> ₹100,000 spend)
    assert m["eligible_customers"] == 14

    # 10. Number of Push items
    assert m["push_items"] == 18

    # 11. Number of customer targets generated
    assert m["customer_targets_generated"] == 163


def test_audit_table_structure_and_coverage(sample_pipeline_output):
    raw, val, analysis, targets = sample_pipeline_output
    audit = build_audit_trail(raw, val, analysis, targets)
    df = audit["table"]

    # Must contain exactly 11 steps
    assert len(df) == 11

    expected_metrics = [
        "Number of uploaded records",
        "Number of exact duplicates detected",
        "Number of duplicates removed",
        "Number of SKU formatting corrections",
        "Number of customer ID formatting corrections",
        "Number of SWITCH mappings",
        "Number of inactive items excluded",
        "Number of inactive items still holding stock",
        "Number of eligible customers",
        "Number of Push items",
        "Number of customer targets generated",
    ]

    for idx, expected_name in enumerate(expected_metrics):
        assert df.iloc[idx]["Audit Metric"] == expected_name
        assert df.iloc[idx]["Step"] == idx + 1
        assert len(str(df.iloc[idx]["Operational Detail"])) > 0
        assert len(str(df.iloc[idx]["Stage"])) > 0


def test_audit_trail_section_present_in_app():
    with open("app.py", "r", encoding="utf-8") as f:
        content = f.read()

    assert "Analysis Audit" in content
    assert "build_audit_trail" in content
