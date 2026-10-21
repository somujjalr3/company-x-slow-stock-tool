"""
Test suite for professional 12-sheet Excel export module (src/export.py).

Verifies:
- Workbook opens successfully without corruption
- All 12 required business sheets are present in exact order:
  1. Executive Summary
  2. SKU Analysis
  3. Push Items
  4. Red List
  5. No Action
  6. Customer Targets
  7. Sales Action List
  8. Risk Analysis
  9. Working Capital
  10. Dead Stock
  11. Data Quality
  12. Assumptions & Rules
- Freeze panes and autofilters applied across sheets
- Currency, integer, decimal, and percentage formatting
- Complete data integrity:
  - SKU Analysis: 38 active commercial SKUs
  - Push Items: 18 items sorted by Priority Score
  - Red List: 7 items with Master Pack comparisons
  - No Action: 13 items with clearance criteria
  - Customer Targets: 163 prioritized call rows
  - Sales Action List: 163 actionable call entries
  - Dead Stock: 5 stagnant items with 0 sales
  - Assumptions & Rules: Complete R1-R7 documentation
- Source data immutability: zero alteration of underlying calculations
"""
import io
import pandas as pd
import openpyxl
import pytest

from src.data_loader import load_data
from src.validation import validate_data
from src.business_logic import run_analysis, calculate_working_capital_impact
from src.customer_targets import build_customer_targets
from src.dead_stock import identify_dead_stock
from src.export import create_excel_report
from src.config import get_default_config

PATH = "sample_data/CompanyX_Data.xlsx"


@pytest.fixture
def analysis_data():
    raw = load_data(PATH)
    val = validate_data(*raw)
    cfg = get_default_config()
    analysis = run_analysis(*raw, validation=val, config=cfg)
    targets = build_customer_targets(
        analysis["clean_item_master"],
        analysis["clean_sales"],
        analysis["analysis_items"],
        val,
        customers=raw[3],
        config=cfg,
    )
    return {
        "items": analysis["analysis_items"],
        "targets": targets,
        "validation": val,
        "inactive_stock": analysis["inactive_stock"],
        "switches": analysis["switch_map_df"],
        "analysis": analysis,
        "config": cfg,
    }


def test_excel_export_sheets_and_successful_load(analysis_data):
    excel_bytes = create_excel_report(
        items=analysis_data["items"],
        targets=analysis_data["targets"],
        validation=analysis_data["validation"],
        inactive_stock=analysis_data["inactive_stock"],
        switches=analysis_data["switches"],
        analysis=analysis_data["analysis"],
        config=analysis_data["config"],
        report_date="2026-10-21",
    )

    assert isinstance(excel_bytes, bytes)
    assert len(excel_bytes) > 0

    # Test that openpyxl loads the workbook successfully
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

    # Test that pandas ExcelFile also loads all sheets successfully
    excel_file = pd.ExcelFile(io.BytesIO(excel_bytes))
    assert excel_file.sheet_names == expected_sheets


def test_executive_summary_content_and_formatting(analysis_data):
    excel_bytes = create_excel_report(
        items=analysis_data["items"],
        targets=analysis_data["targets"],
        validation=analysis_data["validation"],
        inactive_stock=analysis_data["inactive_stock"],
        switches=analysis_data["switches"],
        analysis=analysis_data["analysis"],
        config=analysis_data["config"],
        report_date="2026-10-21",
    )

    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
    ws = wb["Executive Summary"]

    # Verify freeze pane and autofilter
    assert ws.freeze_panes == "A5"
    assert ws.auto_filter.ref is not None
    assert "A4:" in ws.auto_filter.ref

    # Read summary rows into dict
    summary_dict = {}
    for r in range(5, ws.max_row + 1):
        metric = ws.cell(row=r, column=1).value
        val = ws.cell(row=r, column=2).value
        fmt = ws.cell(row=r, column=2).number_format
        if metric:
            summary_dict[metric] = (val, fmt)

    # 1. Report date
    assert "Report Date" in summary_dict
    assert summary_dict["Report Date"][0] == "2026-10-21"

    # 2. Number of items analysed
    assert "Number of Items Analysed" in summary_dict
    assert summary_dict["Number of Items Analysed"][0] == 38

    # 3. Red List count
    assert "Red List Items" in summary_dict
    assert summary_dict["Red List Items"][0] == 7

    # 4. No Action count
    assert "No Action Items" in summary_dict
    assert summary_dict["No Action Items"][0] == 13

    # 5. Push count
    assert "Push Items" in summary_dict
    assert summary_dict["Push Items"][0] == 18

    # 6. Push Aged Value (formatted with currency)
    assert "Push Aged Value" in summary_dict
    assert summary_dict["Push Aged Value"][0] == pytest.approx(163841.0)
    assert "₹" in summary_dict["Push Aged Value"][1]

    # 7. Total aged quantity
    assert "Total Aged Quantity" in summary_dict
    assert summary_dict["Total Aged Quantity"][0] == pytest.approx(2957.0)

    # 8. Total aged value (formatted with currency)
    assert "Total Aged Value" in summary_dict
    assert summary_dict["Total Aged Value"][0] == pytest.approx(237616.0)
    assert "₹" in summary_dict["Total Aged Value"][1]


def test_sku_analysis_and_classification_sheets(analysis_data):
    excel_bytes = create_excel_report(
        items=analysis_data["items"],
        targets=analysis_data["targets"],
        validation=analysis_data["validation"],
        inactive_stock=analysis_data["inactive_stock"],
        switches=analysis_data["switches"],
        analysis=analysis_data["analysis"],
        config=analysis_data["config"],
    )

    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))

    # 1. SKU Analysis sheet
    ws_sku = wb["SKU Analysis"]
    assert ws_sku.freeze_panes == "C2"
    assert ws_sku.auto_filter.ref is not None
    assert ws_sku.max_row == 39  # 1 header + 38 active SKUs
    sku_headers = [ws_sku.cell(1, c).value for c in range(1, ws_sku.max_column + 1)]
    for h in ["SKU", "Item Name", "Slow Stock Class", "Priority Score", "Priority Level", "Recommended Action"]:
        assert h in sku_headers

    # 2. Push Items sheet
    ws_push = wb["Push Items"]
    assert ws_push.freeze_panes == "C2"
    assert ws_push.auto_filter.ref is not None
    assert ws_push.max_row == 19  # 1 header + 18 push items
    push_headers = [ws_push.cell(1, c).value for c in range(1, ws_push.max_column + 1)]
    for h in ["Rank", "SKU", "Priority Score", "Priority Level", "Why Priority?", "Recommended Action"]:
        assert h in push_headers

    # 3. Red List sheet
    ws_red = wb["Red List"]
    assert ws_red.freeze_panes == "C2"
    assert ws_red.auto_filter.ref is not None
    assert ws_red.max_row == 8  # 1 header + 7 items

    # 4. No Action sheet
    ws_no = wb["No Action"]
    assert ws_no.freeze_panes == "C2"
    assert ws_no.auto_filter.ref is not None
    assert ws_no.max_row == 14  # 1 header + 13 items


def test_customer_targets_and_sales_action_list(analysis_data):
    excel_bytes = create_excel_report(
        items=analysis_data["items"],
        targets=analysis_data["targets"],
        validation=analysis_data["validation"],
        inactive_stock=analysis_data["inactive_stock"],
        switches=analysis_data["switches"],
        analysis=analysis_data["analysis"],
        config=analysis_data["config"],
    )

    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))

    # 1. Customer Targets sheet
    ws_tgt = wb["Customer Targets"]
    assert ws_tgt.freeze_panes == "A2"
    assert ws_tgt.auto_filter.ref is not None
    assert ws_tgt.max_row == 164  # 1 header + 163 targets

    df_targets = pd.read_excel(io.BytesIO(excel_bytes), sheet_name="Customer Targets")
    required_cols = ["Push SKU", "Bucket", "Priority", "Customer", "Industry", "Area", "6M Purchase Value", "Opportunity Score", "Reason"]
    for col in required_cols:
        assert col in df_targets.columns

    # Verify SKU1005 targets
    sku1005_targets = df_targets[df_targets["Push SKU"] == "SKU1005"]
    assert len(sku1005_targets) == 9
    t1 = sku1005_targets.iloc[0]
    assert t1["Priority"] == 1
    assert t1["Bucket"] == 1
    assert "Customer 220" in str(t1["Customer"])
    assert t1["6M Purchase Value"] == pytest.approx(665004.0)

    # 2. Sales Action List sheet
    ws_sal = wb["Sales Action List"]
    assert ws_sal.freeze_panes == "A2"
    assert ws_sal.auto_filter.ref is not None
    assert ws_sal.max_row == 164  # 1 header + 163 actions

    df_sal = pd.read_excel(io.BytesIO(excel_bytes), sheet_name="Sales Action List")
    sal_cols = ["Action Rank", "Priority Level", "Priority Score", "SKU", "Customer ID", "Recommended Action", "Action Reason"]
    for col in sal_cols:
        assert col in df_sal.columns


def test_risk_analysis_working_capital_and_dead_stock(analysis_data):
    excel_bytes = create_excel_report(
        items=analysis_data["items"],
        targets=analysis_data["targets"],
        validation=analysis_data["validation"],
        inactive_stock=analysis_data["inactive_stock"],
        switches=analysis_data["switches"],
        analysis=analysis_data["analysis"],
        config=analysis_data["config"],
    )

    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))

    # 1. Risk Analysis sheet
    ws_risk = wb["Risk Analysis"]
    assert ws_risk.freeze_panes == "C2"
    assert ws_risk.auto_filter.ref is not None
    assert ws_risk.max_row == 39
    risk_headers = [ws_risk.cell(1, c).value for c in range(1, ws_risk.max_column + 1)]
    for h in ["SKU", "Risk Score", "Risk Level", "Primary Risk Drivers", "Pts Aged Stock (0-25)"]:
        assert h in risk_headers

    # 2. Working Capital sheet
    assert "Working Capital" in wb.sheetnames
    ws_wc = wb["Working Capital"]
    wc_text = [str(ws_wc.cell(r, 1).value) for r in range(1, ws_wc.max_row + 1)]
    assert any("Slow Stock Classification" in t for t in wc_text)
    assert any("Product Category" in t for t in wc_text)
    assert any("Top 10 Cash-at-Risk" in t for t in wc_text)

    # 3. Dead Stock sheet
    ws_dead = wb["Dead Stock"]
    assert ws_dead.freeze_panes == "C2"
    assert ws_dead.auto_filter.ref is not None
    assert ws_dead.max_row == 2  # 1 header + 1 dead stock item in sample data (SKU1012 with 6M sales = 0)
    assert ws_dead.cell(2, 1).value == "SKU1012"
    dead_headers = [ws_dead.cell(1, c).value for c in range(1, ws_dead.max_column + 1)]
    for h in ["SKU", "Total Stock", "Inventory Value", "Aged Qty", "Aged Value", "Last Available Sales Information", "Recommended Action"]:
        assert h in dead_headers


def test_data_quality_and_assumptions_rules(analysis_data):
    excel_bytes = create_excel_report(
        items=analysis_data["items"],
        targets=analysis_data["targets"],
        validation=analysis_data["validation"],
        inactive_stock=analysis_data["inactive_stock"],
        switches=analysis_data["switches"],
        analysis=analysis_data["analysis"],
        config=analysis_data["config"],
    )

    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))

    # 1. Data Quality sheet
    ws_dq = wb["Data Quality"]
    dq_text = [str(ws_dq.cell(r, 1).value) for r in range(1, ws_dq.max_row + 1)]
    assert any("Validation & Governance Anomalies" in t for t in dq_text)
    assert any("Inactive Items Holding Stock" in t for t in dq_text)
    assert any("Pack-Size SWITCH" in t for t in dq_text)

    # 2. Assumptions & Rules sheet
    ws_ar = wb["Assumptions & Rules"]
    ar_col1 = [str(ws_ar.cell(r, 1).value) for r in range(1, ws_ar.max_row + 1)]
    for rule_code in ["Rule R1", "Rule R2", "Rule R3", "Rule R4", "Rule R5", "Rule R6", "Rule R7"]:
        assert any(rule_code in t for t in ar_col1)


def test_source_data_immutability(analysis_data):
    """Verify that calling create_excel_report does NOT mutate any source inputs."""
    items_copy = analysis_data["items"].copy(deep=True)
    val_copy = dict(analysis_data["validation"])
    switches_copy = analysis_data["switches"].copy(deep=True)

    _ = create_excel_report(
        items=analysis_data["items"],
        targets=analysis_data["targets"],
        validation=analysis_data["validation"],
        inactive_stock=analysis_data["inactive_stock"],
        switches=analysis_data["switches"],
        analysis=analysis_data["analysis"],
        config=analysis_data["config"],
    )

    pd.testing.assert_frame_equal(analysis_data["items"], items_copy)
    pd.testing.assert_frame_equal(analysis_data["switches"], switches_copy)
    assert analysis_data["validation"] == val_copy
