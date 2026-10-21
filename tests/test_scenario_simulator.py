"""
Unit tests for What-If Scenario Simulator (src/scenario_simulator.py).

Verifies:
1. 10%, 25%, 50%, and custom sales uplift simulations.
2. Accurate calculations for:
   - Current Avg Monthly Sales vs Simulated Avg Monthly Sales
   - Current Months to Clear vs Simulated Months to Clear
   - Current Classification vs Simulated Operational Status
   - Estimated stock clearance improvement (months saved, % faster clearance, units/month)
3. Operational status transitions (e.g. SKU1006 moving from Push to No Action at 50% uplift).
4. Strict dataset invariance (simulations are 100% reversible and never mutate the source data).
5. Depletion schedule trajectory generation.
6. Portfolio-wide simulation aggregation.
"""

import math
import pytest
import pandas as pd

from src.data_loader import load_data
from src.validation import validate_data
from src.business_logic import run_analysis
from src.scenario_simulator import (
    simulate_sku_sales_uplift,
    simulate_portfolio_uplift,
)

SAMPLE_PATH = "sample_data/CompanyX_Data.xlsx"


@pytest.fixture(scope="module")
def items_data():
    raw = load_data(SAMPLE_PATH)
    val = validate_data(*raw)
    res = run_analysis(*raw, validation=val)
    return res["analysis_items"]


def test_01_simulate_10_percent_uplift(items_data):
    """Test standard 10% sales uplift simulation on Push SKU1006."""
    item = items_data[items_data["SKU"] == "SKU1006"].iloc[0]
    sim = simulate_sku_sales_uplift(item, 10.0)

    cur_avg = float(item["Avg Monthly Sales"])
    cur_mtc = float(item["Months to Clear"])
    stock = float(item["Total Stock"])

    # Avg sales should be exactly 10% higher
    assert sim["current_avg_monthly_sales"] == pytest.approx(cur_avg)
    assert sim["simulated_avg_monthly_sales"] == pytest.approx(cur_avg * 1.10)

    # Months to Clear should be Total Stock / (Avg Sales * 1.10)
    expected_sim_mtc = stock / (cur_avg * 1.10)
    assert sim["current_months_to_clear"] == pytest.approx(cur_mtc)
    assert sim["simulated_months_to_clear"] == pytest.approx(expected_sim_mtc)

    # Classification: at 10% uplift, MTC is ~3.62 months, still > 3.0 -> Push
    assert sim["current_classification"] == "Push"
    assert sim["simulated_operational_status"] == "Push"
    assert sim["status_changed"] is False

    # Clearance improvement
    assert sim["runway_reduction_months"] == pytest.approx(cur_mtc - expected_sim_mtc)
    assert sim["additional_monthly_units"] == pytest.approx(cur_avg * 0.10)


def test_02_simulate_25_percent_uplift(items_data):
    """Test standard 25% sales uplift simulation."""
    item = items_data[items_data["SKU"] == "SKU1005"].iloc[0]
    sim = simulate_sku_sales_uplift(item, 25.0)

    cur_avg = float(item["Avg Monthly Sales"])
    cur_mtc = float(item["Months to Clear"])

    assert sim["simulated_avg_monthly_sales"] == pytest.approx(cur_avg * 1.25)
    assert sim["runway_reduction_months"] > 0
    assert sim["runway_reduction_pct"] == pytest.approx(20.0, rel=1e-2)  # 1 - 1/1.25 = 0.20
    assert sim["current_classification"] == "Push"
    assert sim["simulated_operational_status"] == "Push"


def test_03_simulate_50_percent_uplift_status_transition(items_data):
    """Test 50% uplift causing SKU1006 runway to drop below 3.0 months -> No Action."""
    item = items_data[items_data["SKU"] == "SKU1006"].iloc[0]
    sim = simulate_sku_sales_uplift(item, 50.0)

    cur_mtc = float(item["Months to Clear"])
    assert cur_mtc > 3.0  # 3.98 months

    # Under 50% uplift, simulated MTC drops to 2.65 months (< 3.0)
    assert sim["simulated_months_to_clear"] < 3.0
    assert sim["current_classification"] == "Push"
    assert sim["simulated_operational_status"] == "No Action"
    assert sim["status_changed"] is True
    assert "transitions from PUSH to NO ACTION" in sim["clearance_summary"]


def test_04_simulate_custom_uplift(items_data):
    """Test arbitrary custom sales uplift percentage (e.g. 35%)."""
    item = items_data[items_data["SKU"] == "SKU1019"].iloc[0]
    sim = simulate_sku_sales_uplift(item, 35.0)

    cur_avg = float(item["Avg Monthly Sales"])
    assert sim["uplift_pct"] == 35.0
    assert sim["simulated_avg_monthly_sales"] == pytest.approx(cur_avg * 1.35)
    assert sim["additional_monthly_units"] == pytest.approx(cur_avg * 0.35)


def test_05_source_data_invariance(items_data):
    """Ensure that simulation never mutates the source DataFrame or R1-R7 classifications."""
    counts_before = items_data["Class"].value_counts().to_dict()

    # Run heavy simulation
    for uplift in [10, 25, 50, 100]:
        for _, row in items_data.iterrows():
            _ = simulate_sku_sales_uplift(row, uplift)

    counts_after = items_data["Class"].value_counts().to_dict()

    # R1-R7 invariant benchmarks
    assert counts_before == counts_after
    assert counts_after["Red List"] == 7
    assert counts_after["No Action"] == 13
    assert counts_after["Push"] == 18


def test_06_depletion_schedule_integrity(items_data):
    """Verify that depletion trajectory schedule starts at Total Stock and decreases monotonically."""
    item = items_data[items_data["SKU"] == "SKU1006"].iloc[0]
    sim = simulate_sku_sales_uplift(item, 25.0)

    schedule = sim["depletion_schedule"]
    assert len(schedule) >= 12
    assert schedule[0]["Month"] == 0
    assert schedule[0]["Current Pace Stock"] == float(item["Total Stock"])
    assert schedule[0]["Simulated Pace Stock"] == float(item["Total Stock"])

    # Simulated pace should always deplete faster or equal to current pace
    for pt in schedule:
        assert pt["Simulated Pace Stock"] <= pt["Current Pace Stock"]
        assert pt["Simulated Pace Stock"] >= 0.0
        assert pt["Current Pace Stock"] >= 0.0


def test_07_portfolio_simulation(items_data):
    """Test portfolio-wide uplift simulation."""
    res = simulate_portfolio_uplift(items_data, 50.0)
    summary = res["summary"]
    sim_df = res["simulated_items"]

    assert summary["total_skus"] == 38
    assert summary["current_push_count"] == 18
    # Under 50% uplift, several Push items clear below 3.0 months runway
    assert summary["push_cleared_to_noaction"] > 0
    assert summary["simulated_push_count"] < 18
    assert summary["total_additional_monthly_capital"] > 0
    assert len(sim_df) == 38
