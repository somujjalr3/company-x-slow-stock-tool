"""
Test suite for AI Management Assistant (src/ai_management_assistant.py).

Verifies:
1. The AI does NOT calculate financial metrics.
2. The AI does NOT classify SKUs.
3. The AI does NOT determine Rules R1-R7.
4. The AI only interprets already-calculated deterministic outputs.
5. Responses reference actual calculated values and never invent numbers.
6. Returns 'Insufficient data available.' when information is absent or unknown.
7. Prominent interpretation layer disclaimer is present in context and outputs.
8. Supports all 5 canonical executive questions:
   - 'Which five items should we prioritize?'
   - 'Why is SKU1006 important?'
   - 'Which categories have the highest aged inventory?'
   - 'What are the biggest working capital risks?'
   - 'Which customers should sales contact?'
"""

import pytest
import pandas as pd
import re

from src.data_loader import load_data
from src.validation import validate_data
from src.business_logic import run_analysis
from src.customer_targets import build_customer_targets
from src.config import get_default_config
from src.ai_management_assistant import (
    build_management_structured_context,
    interpret_management_query,
    AI_DISCLAIMER,
)

PATH = "sample_data/CompanyX_Data.xlsx"


@pytest.fixture
def management_context():
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
    context = build_management_structured_context(
        items=analysis["analysis_items"],
        targets=targets,
        working_capital=analysis["working_capital"],
        dead_stock=analysis["dead_stock"],
        config=cfg,
        sales_trends=analysis.get("sales_trends"),
        sales_df=analysis.get("clean_sales"),
    )
    return context, analysis, targets


def test_structured_context_contains_all_deterministic_dimensions(management_context):
    context, analysis, _ = management_context

    assert "kpis" in context
    assert "top_push_items" in context
    assert "sku_catalog" in context
    assert "categories" in context
    assert "top_cash_at_risk" in context
    assert "customer_opportunities" in context
    assert "dead_stock" in context
    assert "disclaimer" in context

    kpis = context["kpis"]
    assert kpis["total_skus"] == 38
    assert kpis["push_skus"] == 18
    assert kpis["red_list_skus"] == 7
    assert kpis["no_action_skus"] == 13
    assert kpis["total_aged_value"] == pytest.approx(237616.0)
    assert kpis["push_aged_value"] == pytest.approx(163841.0)
    assert kpis["push_aged_share_pct"] == pytest.approx(68.9, abs=0.1)
    assert kpis["dead_stock_skus"] == 1
    assert kpis["dead_stock_aged_value"] == pytest.approx(16660.0)


def test_mandatory_disclaimer_present(management_context):
    context, _, _ = management_context
    assert AI_DISCLAIMER in context["disclaimer"]

    res = interpret_management_query("Which five items should we prioritize?", context)
    assert "Interpretation Layer Disclaimer" in res["disclaimer"]
    assert "does NOT calculate financial metrics" in res["disclaimer"]
    assert "does NOT classify SKUs" in res["disclaimer"]
    assert "does NOT determine Rules R1–R7" in res["disclaimer"]


def test_question_which_five_items_should_we_prioritize(management_context):
    context, _, _ = management_context
    res = interpret_management_query("Which five items should we prioritize?", context)

    assert res["status"] == "SUCCESS"
    answer = res["answer"]

    # Must reference the exact top 5 Push SKUs
    expected_top_5 = ["SKU1005", "SKU1034", "SKU1020", "SKU1038", "SKU1036"]
    for sku in expected_top_5:
        assert sku in answer

    # Verify Priority Scores
    assert "84/100" in answer  # SKU1005 Priority Score
    assert "80/100" in answer  # SKU1034 Priority Score
    assert "79/100" in answer  # SKU1020 Priority Score

    # Verify Aged Values
    assert "31,280" in answer  # SKU1005
    assert "20,315" in answer  # SKU1034
    assert "18,360" in answer  # SKU1020

    # Verify referenced metrics structure
    ref = res["referenced_metrics"]
    assert len(ref) == 5
    assert ref["Rank 1"]["SKU"] == "SKU1005"
    assert ref["Rank 1"]["Priority Score"] == 84
    assert ref["Rank 2"]["SKU"] == "SKU1034"


def test_question_why_is_sku1006_important(management_context):
    context, _, _ = management_context
    res = interpret_management_query("Why is SKU1006 important?", context)

    assert res["status"] == "SUCCESS"
    answer = res["answer"]

    # Must mention SKU1006 and its exact properties
    assert "SKU1006" in answer
    assert "A-Product 06" in answer
    assert "Push" in answer
    assert "9,150" in answer  # Aged Value
    assert "30,450" in answer  # Total Inventory Value
    assert "4.0 months" in answer  # Months to Clear
    assert "47/100" in answer  # Priority Score
    assert "41/100" in answer  # Risk Score
    assert "Medium" in answer

    ref = res["referenced_metrics"]
    assert ref["SKU"] == "SKU1006"
    assert ref["Classification"] == "Push"
    assert "₹9,150" in ref["Aged Inventory Value"]


def test_question_which_categories_have_highest_aged_inventory(management_context):
    context, _, _ = management_context
    res = interpret_management_query("Which categories have the highest aged inventory?", context)

    assert res["status"] == "SUCCESS"
    answer = res["answer"]

    # Must reference Category C (Rank 1) and Category E (Rank 2)
    assert "Category C" in answer
    assert "68,630" in answer
    assert "28.9%" in answer

    assert "Category E" in answer
    assert "45,395" in answer
    assert "19.1%" in answer

    assert "Category A" in answer
    assert "43,365" in answer
    assert "18.3%" in answer

    # Verify ranking in referenced metrics
    ref = res["referenced_metrics"]
    assert ref["Category C"]["Rank"] == 1
    assert ref["Category E"]["Rank"] == 2
    assert ref["Category A"]["Rank"] == 3


def test_question_what_are_the_biggest_working_capital_risks(management_context):
    context, _, _ = management_context
    res = interpret_management_query("What are the biggest working capital risks?", context)

    assert res["status"] == "SUCCESS"
    answer = res["answer"]

    # Total Cash at Risk
    assert "237,616" in answer
    # Push aged capital
    assert "163,841" in answer
    assert "69.0%" in answer
    # Red List inventory value
    assert "109,270" in answer

    # Must reference top cash-at-risk items
    assert "SKU1005" in answer
    assert "31,280" in answer
    assert "SKU1034" in answer
    assert "SKU1017" in answer
    assert "SKU1020" in answer
    assert "SKU1012" in answer


def test_question_which_customers_should_sales_contact(management_context):
    context, _, _ = management_context
    res = interpret_management_query("Which customers should sales contact?", context)

    assert res["status"] == "SUCCESS"
    answer = res["answer"]

    # Top target: Customer 220 (C220) for SKU1005
    assert "Customer 220" in answer or "C220" in answer
    assert "SKU1005" in answer
    assert "665,004" in answer
    assert "Bucket 1" in answer
    assert "95/100" in answer  # Opportunity Score

    # Bucket prioritization guidance
    assert "Bucket 1 accounts" in answer


def test_insufficient_data_for_unknown_sku(management_context):
    context, _, _ = management_context
    res = interpret_management_query("Why is SKU9999 important?", context)

    assert res["status"] == "INSUFFICIENT_DATA"
    assert "Insufficient data available" in res["answer"]
    assert "SKU9999" in res["answer"] or "SKU 'SKU9999'" in res["answer"]


def test_insufficient_data_for_unrelated_or_empty_query(management_context):
    context, _, _ = management_context

    res_empty = interpret_management_query("", context)
    assert res_empty["status"] == "INSUFFICIENT_DATA"
    assert "Insufficient data available" in res_empty["answer"]

    res_random = interpret_management_query("What is the weather in Mumbai tomorrow?", context)
    assert res_random["status"] == "INSUFFICIENT_DATA"
    assert "Insufficient data available" in res_random["answer"]


def test_dead_stock_inquiry(management_context):
    context, _, _ = management_context
    res = interpret_management_query("What dead stock items do we have?", context)

    assert res["status"] == "SUCCESS"
    answer = res["answer"]
    assert "SKU1012" in answer
    assert "55,420" in answer
    assert "16,660" in answer
    assert "1 Dead Stock SKU" in answer


def test_ai_does_not_mutate_context_or_invent_metrics(management_context):
    context, _, _ = management_context

    # Query 1
    _ = interpret_management_query("Which five items should we prioritize?", context)
    # Query 2
    _ = interpret_management_query("Why is SKU1006 important?", context)

    # Invariants check: KPIs in context remain unchanged
    assert context["kpis"]["push_skus"] == 18
    assert context["kpis"]["total_aged_value"] == pytest.approx(237616.0)
    assert context["sku_catalog"]["SKU1006"]["aged_value"] == 9150.0
    assert context["sku_catalog"]["SKU1006"]["classification"] == "Push"
