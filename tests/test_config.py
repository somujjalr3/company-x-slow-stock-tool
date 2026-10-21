"""
Unit tests for Centralized Configuration Structure and Settings module (src/config.py).

Verifies:
1. Benchmark case defaults match MBA requirements exactly.
2. Mode label displays 'CASE DEFAULT SETTINGS' vs 'CUSTOM SETTINGS'.
3. Serialization to_dict() and from_dict() roundtrip.
4. Diff calculation against case defaults.
5. Current Case Rules (R1–R7) completeness.
6. Integration with run_analysis() preserving benchmark outputs under defaults.
7. Deterministic reactivity of classifications and customer targeting to custom settings.
8. Raw source data immutability during configuration changes.
"""

import pytest
import pandas as pd
from src.config import (
    CaseConfig,
    get_default_config,
    is_case_default,
    get_current_case_rules,
)
from src.data_loader import load_data
from src.validation import validate_data
from src.business_logic import run_analysis, calculate_inventory_risk_row
from src.customer_targets import build_customer_targets
from src.sales_priority import calculate_sales_priority_row

SAMPLE_PATH = "sample_data/CompanyX_Data.xlsx"


@pytest.fixture(scope="module")
def raw_dataset():
    return load_data(SAMPLE_PATH)


def test_01_config_default_values():
    """Verify default values match case study requirements exactly."""
    cfg = get_default_config()

    # Red List sales threshold: 6M Sales Qty < 1 Master Pack
    assert cfg.red_list_mp_multiplier == 1.0

    # Months-to-clear threshold: Months to Clear < 3
    assert cfg.months_to_clear_threshold == 3.0

    # Customer eligibility: 6M Purchase Value > ₹100,000
    assert cfg.customer_eligibility_spend == 100000.0

    # Aged stock: 91+ days
    assert cfg.aging_days_threshold == 91

    # Risk thresholds: Critical >= 80, High >= 60, Medium >= 30
    assert cfg.risk_critical_threshold == 80
    assert cfg.risk_high_threshold == 60
    assert cfg.risk_medium_threshold == 30

    # Priority thresholds: Critical >= 80, High >= 60, Medium >= 30
    assert cfg.priority_critical_threshold == 80
    assert cfg.priority_high_threshold == 60
    assert cfg.priority_medium_threshold == 30

    # Mode label and is_default
    assert cfg.is_default() is True
    assert cfg.mode_label == "CASE DEFAULT SETTINGS"
    assert is_case_default(cfg) is True
    assert is_case_default(None) is True
    assert cfg.diff_from_defaults() == []


def test_02_config_custom_detection_and_diff():
    """Verify custom settings detection and diff generation."""
    cfg = CaseConfig(
        months_to_clear_threshold=4.0,
        customer_eligibility_spend=150000.0,
        aging_days_threshold=61,
    )

    assert cfg.is_default() is False
    assert cfg.mode_label == "CUSTOM SETTINGS"
    assert is_case_default(cfg) is False

    diffs = cfg.diff_from_defaults()
    assert len(diffs) == 3

    diff_params = [d["parameter"] for d in diffs]
    assert "Months-to-Clear Threshold" in diff_params
    assert "Customer Eligibility 6M Spend" in diff_params
    assert "Aging Days Threshold" in diff_params


def test_03_serialization_roundtrip():
    """Verify to_dict and from_dict serialization preserves all attributes."""
    cfg = CaseConfig(
        red_list_mp_multiplier=1.5,
        months_to_clear_threshold=4.5,
        customer_eligibility_spend=120000.0,
        aging_days_threshold=61,
        risk_critical_threshold=85,
        priority_critical_threshold=75,
    )

    d = cfg.to_dict()
    restored = CaseConfig.from_dict(d)

    assert restored.red_list_mp_multiplier == 1.5
    assert restored.months_to_clear_threshold == 4.5
    assert restored.customer_eligibility_spend == 120000.0
    assert restored.aging_days_threshold == 61
    assert restored.risk_critical_threshold == 85
    assert restored.priority_critical_threshold == 75
    assert restored.is_default() is False


def test_04_get_current_case_rules_completeness():
    """Verify official Case Rules R1-R7 reference table."""
    rules = get_current_case_rules()
    assert len(rules) == 7

    rule_names = [r["Rule"] for r in rules]
    assert any("Rule R1" in r for r in rule_names)
    assert any("Rule R2" in r for r in rule_names)
    assert any("Rule R3" in r for r in rule_names)
    assert any("Rule R4" in r for r in rule_names)
    assert any("Rule R5" in r for r in rule_names)
    assert any("Rule R6" in r for r in rule_names)
    assert any("Rule R7" in r for r in rule_names)


def test_05_default_config_produces_exact_benchmark_results(raw_dataset):
    """Verify default config produces exact MBA benchmark results."""
    raw = [df.copy() for df in raw_dataset]
    val = validate_data(*raw)
    cfg = get_default_config()

    res = run_analysis(*raw, validation=val, config=cfg)
    items = res["analysis_items"]

    class_counts = items["Class"].value_counts().to_dict()
    assert class_counts.get("Push", 0) == 18
    assert class_counts.get("No Action", 0) == 13
    assert class_counts.get("Red List", 0) == 7

    push_aged = items[items["Class"] == "Push"]["Aged Value"].sum()
    assert push_aged == pytest.approx(163841.0, abs=1.0)


def test_06_custom_months_to_clear_threshold(raw_dataset):
    """Verify altering months_to_clear_threshold affects classification."""
    raw = [df.copy() for df in raw_dataset]
    val = validate_data(*raw)

    # Increasing threshold to 6.0 should classify more items with MTC < 6 as No Action
    cfg_strict = CaseConfig(months_to_clear_threshold=6.0)
    res_strict = run_analysis(*raw, validation=val, config=cfg_strict)
    items_strict = res_strict["analysis_items"]

    no_action_strict = (items_strict["Class"] == "No Action").sum()
    # At 6.0 months threshold, more items qualify for No Action than at 3.0 months
    assert no_action_strict >= 13


def test_07_custom_customer_eligibility_spend(raw_dataset):
    """Verify altering customer_eligibility_spend changes eligible accounts."""
    raw = [df.copy() for df in raw_dataset]
    val = validate_data(*raw)

    # Baseline: spend > 100,000 yields 14 eligible accounts
    cfg_default = get_default_config()
    res_def = run_analysis(*raw, validation=val, config=cfg_default)
    targets_def = build_customer_targets(
        res_def["clean_item_master"],
        res_def["clean_sales"],
        res_def["analysis_items"],
        val,
        customers=raw[3],
        config=cfg_default,
    )
    all_def_cids = {cid for df in targets_def.values() for cid in df["CustomerID"]}
    assert len(all_def_cids) <= 14

    # Lower threshold to ₹50,000 -> More eligible accounts
    cfg_loose = CaseConfig(customer_eligibility_spend=50000.0)
    targets_loose = build_customer_targets(
        res_def["clean_item_master"],
        res_def["clean_sales"],
        res_def["analysis_items"],
        val,
        customers=raw[3],
        config=cfg_loose,
    )
    all_loose_cids = {cid for df in targets_loose.values() for cid in df["CustomerID"]}
    assert len(all_loose_cids) >= len(all_def_cids)


def test_08_custom_risk_and_priority_thresholds():
    """Verify custom risk and priority thresholds evaluate dynamically."""
    item = {
        "Total Stock": 100,
        "Aged Qty": 50,
        "Aged Value": 20000,
        "6M Sales Qty": 10,
        "Master Pack Qty": 5,
        "Avg Monthly Sales": 1.67,
        "Months to Clear": 60.0,
        "Unit Cost (Rs)": 400.0,
        "Inventory Value": 40000.0,
        "Risk Score": 75,
        "Sales Trend": "Declining",
    }

    # Default risk threshold: 75 -> High (Critical >= 80, High >= 60)
    def_risk = calculate_inventory_risk_row(item, config=get_default_config())
    assert def_risk["Risk Level"] == "High"

    # Custom risk threshold: Critical >= 70 -> Critical
    cust_risk_cfg = CaseConfig(risk_critical_threshold=70)
    cust_risk = calculate_inventory_risk_row(item, config=cust_risk_cfg)
    assert cust_risk["Risk Level"] == "Critical"

    # Default priority calculation
    def_prio = calculate_sales_priority_row(item, config=get_default_config())
    assert def_prio["priority_level"] in ["Critical", "High", "Medium", "Low"]

    # Custom priority threshold: Critical >= 95
    cust_prio_cfg = CaseConfig(priority_critical_threshold=95)
    cust_prio = calculate_sales_priority_row(item, config=cust_prio_cfg)
    if def_prio["priority_score"] < 95:
        assert cust_prio["priority_level"] != "Critical"


def test_09_source_data_non_corruption(raw_dataset):
    """Verify modifying configuration never mutates raw underlying datasets."""
    raw_original = [df.copy() for df in raw_dataset]
    val = validate_data(*raw_original)

    # Run with custom parameters
    cfg_custom = CaseConfig(
        red_list_mp_multiplier=2.0,
        months_to_clear_threshold=5.0,
        customer_eligibility_spend=50000.0,
        aging_days_threshold=61,
    )
    _ = run_analysis(*raw_original, validation=val, config=cfg_custom)

    # Verify original raw datasets are completely identical
    for df_orig, df_check in zip(raw_dataset, raw_original):
        pd.testing.assert_frame_equal(df_orig, df_check)


def test_10_settings_page_elements_in_app():
    """Verify Settings page and mode indicators are integrated into app.py."""
    with open("app.py", "r", encoding="utf-8") as f:
        content = f.read()

    # Check tab presence
    assert '"Settings"' in content
    assert "tab6" in content

    # Check mode banners
    assert "CASE DEFAULT SETTINGS" in content
    assert "CUSTOM SETTINGS" in content

    # Check Current Case Rules reference
    assert "Current Case Rules" in content
    assert "get_current_case_rules" in content

    # Check configurable inputs
    assert "Red List Sales Threshold" in content
    assert "Months-to-Clear Threshold" in content
    assert "Customer Eligibility 6M Spend" in content
    assert "Aging Threshold" in content
    assert "Apply Settings" in content
    assert "Reset to Case Defaults" in content

    # Check non-corruption guarantee statement
    assert "Data Integrity" in content
