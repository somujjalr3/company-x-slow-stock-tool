"""
What-If Scenario Simulator Module for Company X Slow Stock Action Tool.

Simulates the operational impact of sales uplifts on slow-moving inventory:
- 10% sales uplift
- 25% sales uplift
- 50% sales uplift
- Custom sales uplift

Calculates:
- Current Avg Monthly Sales vs Simulated Avg Monthly Sales
- Current Months to Clear vs Simulated Months to Clear
- Current Classification vs Simulated Operational Status
- Estimated stock clearance improvement (months saved, units cleared, capital liquidated)
- Projected inventory depletion curves

CRITICAL INVARIANTS:
- Does NOT mutate or overwrite the source dataset.
- Does NOT change the original R1-R7 classifications.
- Clearly demarcated as an exploratory scenario simulation.
- 100% reversible, deterministic Python calculations without AI.
"""

import math
from typing import Dict, List, Tuple, Any, Optional
import numpy as np
import pandas as pd
from src.logger import get_logger
from src.config import CaseConfig, get_default_config

logger = get_logger("ScenarioSimulator")


def simulate_sku_sales_uplift(sku_data, uplift_pct: float, config=None) -> dict:
    """
    Simulates the operational impact of a sales uplift on a single catalog SKU.

    Parameters:
      sku_data: dict or pd.Series with SKU metrics (Total Stock, Unit Cost,
                Avg Monthly Sales, 6M Sales Qty, Master Pack Qty, Aged Qty, Class).
      uplift_pct: float percentage sales uplift (e.g. 10.0 for +10%, 25.0 for +25%).
      config: Optional CaseConfig instance for custom operational thresholds.

    Returns:
      dict containing Current vs Simulated metrics, clearance improvements,
      operational status transitions, and depletion schedule data.
    """
    def _to_float(v, default=0.0):
        try:
            val = float(v)
            return default if (pd.isna(val) or np.isnan(val)) else val
        except (ValueError, TypeError):
            return default

    # Extract base attributes
    sku = str(sku_data.get("SKU", "SKU_UNKNOWN")).strip().upper()
    item_name = str(sku_data.get("Item Name") or sku_data.get("Description", sku))
    category = str(sku_data.get("Category", "Unassigned"))
    total_stock = _to_float(sku_data.get("Total Stock", 0.0))
    unit_cost = _to_float(sku_data.get("Unit Cost (Rs)", 0.0))
    aged_qty = _to_float(sku_data.get("Aged Qty", 0.0))
    aged_val = _to_float(sku_data.get("Aged Value", 0.0))
    if aged_val <= 0.0 and aged_qty > 0 and unit_cost > 0:
        aged_val = aged_qty * unit_cost

    master_pack = _to_float(sku_data.get("Master Pack Qty", 1.0))
    if master_pack <= 0:
        master_pack = 1.0

    # 1. Current Metrics (Invariant Source of Truth)
    cur_class = str(sku_data.get("Class", "Push"))
    cur_avg = _to_float(sku_data.get("Avg Monthly Sales", 0.0))
    cur_6m = _to_float(sku_data.get("6M Sales Qty", 0.0))
    if cur_avg <= 0.0 and cur_6m > 0:
        cur_avg = cur_6m / 6.0

    cur_mtc_raw = sku_data.get("Months to Clear")
    if cur_mtc_raw == float("inf") or (isinstance(cur_mtc_raw, str) and "inf" in str(cur_mtc_raw).lower()):
        cur_mtc = float("inf")
    else:
        cur_mtc = _to_float(cur_mtc_raw, float("inf") if cur_avg <= 0 else (total_stock / cur_avg if total_stock > 0 else 0.0))

    # 2. Simulated Metrics
    pct_factor = 1.0 + (float(uplift_pct) / 100.0)
    sim_avg = max(0.0, cur_avg * pct_factor)
    sim_6m = max(0.0, cur_6m * pct_factor)

    if sim_avg > 0:
        sim_mtc = total_stock / sim_avg if total_stock > 0 else 0.0
    else:
        sim_mtc = float("inf")

    if config is None:
        config = get_default_config()

    # 3. Simulated Operational Status (Evaluation of R5 logic under simulated pace)
    # R5 Order:
    # 1. RED LIST if simulated 6M sales < red_list_mp_multiplier * Master Pack
    # 2. NO ACTION if Aged Qty == 0 OR simulated Months to Clear < months_to_clear_threshold
    # 3. PUSH otherwise
    mtc_thresh = config.months_to_clear_threshold
    mp_thresh = master_pack * config.red_list_mp_multiplier

    if config.is_default():
        if sim_6m < master_pack:
            sim_status = "Red List"
            status_note = f"Simulated 6M sales ({sim_6m:.1f} units) remain below 1 Master Pack ({master_pack:.0f} units)."
        elif aged_qty == 0 or sim_mtc < 3.0:
            sim_status = "No Action"
            if aged_qty == 0:
                status_note = "Zero aged stock in warehouse; healthy velocity."
            else:
                status_note = f"Simulated clearance runway ({sim_mtc:.2f} months) clears below the 3.0-month slow-stock threshold."
        else:
            sim_status = "Push"
            status_note = f"Item still carries aged stock ({aged_qty:,.0f} units) and clearance runway ({sim_mtc:.2f} months) exceeds 3.0 months."
    else:
        if sim_6m < mp_thresh:
            sim_status = "Red List"
            status_note = f"Simulated 6M sales ({sim_6m:.1f} units) remain below threshold ({mp_thresh:.1f} units)."
        elif aged_qty == 0 or sim_mtc < mtc_thresh:
            sim_status = "No Action"
            if aged_qty == 0:
                status_note = "Zero aged stock in warehouse; healthy velocity."
            else:
                status_note = f"Simulated clearance runway ({sim_mtc:.2f} months) clears below the {mtc_thresh:.1f}-month slow-stock threshold."
        else:
            sim_status = "Push"
            status_note = f"Item still carries aged stock ({aged_qty:,.0f} units) and clearance runway ({sim_mtc:.2f} months) exceeds {mtc_thresh:.1f} months."

    # 4. Stock Clearance Improvement
    if math.isinf(cur_mtc) and not math.isinf(sim_mtc):
        runway_reduction_months = float("inf")
        runway_reduction_pct = 100.0
        improvement_headline = f"Accelerated from stagnant / non-clearing (∞) to {sim_mtc:.1f} months runway."
    elif not math.isinf(cur_mtc) and not math.isinf(sim_mtc):
        runway_reduction_months = max(0.0, cur_mtc - sim_mtc)
        runway_reduction_pct = (runway_reduction_months / cur_mtc * 100.0) if cur_mtc > 0 else 0.0
        improvement_headline = f"Runway reduced by {runway_reduction_months:.1f} months ({runway_reduction_pct:.1f}% faster clearance)."
    else:
        runway_reduction_months = 0.0
        runway_reduction_pct = 0.0
        improvement_headline = "No clearance improvement (sales velocity remains zero)."

    add_monthly_units = max(0.0, sim_avg - cur_avg)
    add_monthly_capital = add_monthly_units * unit_cost
    add_6m_units = max(0.0, sim_6m - cur_6m)

    status_changed = (cur_class != sim_status)
    if status_changed:
        transition_desc = f"Operational status transitions from {cur_class.upper()} to {sim_status.upper()}."
    else:
        transition_desc = f"Operational status remains {cur_class.upper()} (clearance timeline accelerated)."

    clearance_summary = (
        f"A {uplift_pct:+.0f}% sales uplift accelerates monthly sales by +{add_monthly_units:.1f} units/month "
        f"(+₹{add_monthly_capital:,.0f}/month), reducing inventory runway from "
        f"{'∞' if math.isinf(cur_mtc) else f'{cur_mtc:.1f}'} to "
        f"{'∞' if math.isinf(sim_mtc) else f'{sim_mtc:.1f}'} months. {transition_desc}"
    )

    # 5. Inventory Depletion Trajectory Curve (over 12-24 months)
    max_horizon = 12
    if not math.isinf(cur_mtc):
        max_horizon = min(24, max(12, int(math.ceil(cur_mtc)) + 2))
    elif not math.isinf(sim_mtc):
        max_horizon = min(24, max(12, int(math.ceil(sim_mtc)) + 2))

    depletion_points = []
    for m in range(0, max_horizon + 1):
        rem_cur = max(0.0, total_stock - m * cur_avg)
        rem_sim = max(0.0, total_stock - m * sim_avg)
        depletion_points.append({
            "Month": m,
            "Current Pace Stock": round(rem_cur, 1),
            "Simulated Pace Stock": round(rem_sim, 1),
        })

    return {
        "sku": sku,
        "item_name": item_name,
        "category": category,
        "uplift_pct": float(uplift_pct),
        "total_stock": total_stock,
        "unit_cost": unit_cost,
        "aged_qty": aged_qty,
        "aged_value": aged_val,
        "master_pack": master_pack,

        # Current vs Simulated Core Metrics
        "current_avg_monthly_sales": cur_avg,
        "simulated_avg_monthly_sales": sim_avg,
        "current_months_to_clear": cur_mtc,
        "simulated_months_to_clear": sim_mtc,
        "current_6m_sales_qty": cur_6m,
        "simulated_6m_sales_qty": sim_6m,
        "current_classification": cur_class,
        "simulated_operational_status": sim_status,

        # Clearance Improvements
        "runway_reduction_months": runway_reduction_months,
        "runway_reduction_pct": runway_reduction_pct,
        "additional_monthly_units": add_monthly_units,
        "additional_monthly_capital": add_monthly_capital,
        "additional_6m_units": add_6m_units,
        "status_changed": status_changed,
        "status_note": status_note,
        "improvement_headline": improvement_headline,
        "clearance_summary": clearance_summary,
        "depletion_schedule": depletion_points,
    }


def simulate_portfolio_uplift(items_df: pd.DataFrame, uplift_pct: float) -> dict:
    """
    Simulates portfolio-wide sales uplift across all active catalog items.
    Pure calculation: does NOT mutate items_df.
    """
    if items_df is None or items_df.empty:
        return {
            "summary": {},
            "simulated_items": pd.DataFrame(),
        }

    rows = []
    for _, item in items_df.iterrows():
        res = simulate_sku_sales_uplift(item, uplift_pct)
        rows.append({
            "SKU": res["sku"],
            "Item Name": res["item_name"],
            "Category": res["category"],
            "Current Class": res["current_classification"],
            "Simulated Status": res["simulated_operational_status"],
            "Status Changed": res["status_changed"],
            "Current Avg Sales": res["current_avg_monthly_sales"],
            "Simulated Avg Sales": res["simulated_avg_monthly_sales"],
            "Current MTC": res["current_months_to_clear"],
            "Simulated MTC": res["simulated_months_to_clear"],
            "Runway Saved (m)": res["runway_reduction_months"],
            "Additional Monthly Units": res["additional_monthly_units"],
            "Additional Monthly Capital": res["additional_monthly_capital"],
            "Aged Value": res["aged_value"],
        })

    sim_df = pd.DataFrame(rows)

    # Portfolio summary
    cur_push = int((sim_df["Current Class"] == "Push").sum())
    sim_push = int((sim_df["Simulated Status"] == "Push").sum())
    push_to_noaction = int(((sim_df["Current Class"] == "Push") & (sim_df["Simulated Status"] == "No Action")).sum())
    total_add_capital = float(sim_df["Additional Monthly Capital"].sum())

    summary = {
        "uplift_pct": float(uplift_pct),
        "total_skus": len(sim_df),
        "current_push_count": cur_push,
        "simulated_push_count": sim_push,
        "push_cleared_to_noaction": push_to_noaction,
        "total_additional_monthly_capital": total_add_capital,
    }

    return {
        "summary": summary,
        "simulated_items": sim_df,
    }
