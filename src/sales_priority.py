"""
Sales Priority Score Module for Company X Slow Stock Action Tool.

Calculates a deterministic 0-100 Sales Priority Score specifically for Push items
to help commercial and sales teams prioritize which slow-stock SKUs to liquidate first.

Methodology Architecture (0-100 Points):
  1. Aged Inventory Value (0-25 pts): Capital trapped in 91+ day aged inventory.
  2. Total Inventory Value (0-15 pts): Total warehouse capital exposure.
  3. Months to Clear (0-20 pts): Inventory runway and clearance timeline.
  4. Sales Trend (0-15 pts): Demand trajectory from Sales_Lines (Declining urgency / Growing conversion).
  5. Sales Velocity (0-10 pts): Turnover pace relative to total inventory.
  6. Risk Score Alignment (0-15 pts): Existing deterministic 0-100 Inventory Risk Score.

Priority Levels:
  - Critical: 80 - 100
  - High:     60 - 79
  - Medium:   30 - 59
  - Low:      0 - 29

CRITICAL INVARIANTS:
  - Does NOT modify Rules R1-R7.
  - Does NOT replace or alter the original Push classification.
  - Strictly deterministic, explainable Python logic. Never uses AI.
"""

from typing import Dict, List, Tuple, Any, Optional, Union
import numpy as np
import pandas as pd
from src.logger import get_logger
from src.config import CaseConfig, get_default_config

logger = get_logger("SalesPriority")


def calculate_sales_priority_row(row, sales_trend=None, config=None):
    """
    Computes deterministic 0-100 Sales Priority Score for an individual catalog SKU.

    Parameters:
      row: dict or pd.Series containing item metrics:
           - Aged Value
           - Inventory Value / Total Stock & Unit Cost
           - Months to Clear
           - Sales Trend
           - Avg Monthly Sales & Total Stock
           - Risk Score
      sales_trend: Optional str override for sales trend.
      config: Optional CaseConfig instance for custom priority thresholds.

    Returns dict containing:
      - 'priority_score': int (0-100)
      - 'priority_level': 'Critical' | 'High' | 'Medium' | 'Low'
      - 'why_priority': Deterministic explanation sentence
      - 'points_breakdown': dict with points for each factor
    """
    def _to_float(v, default=0.0):
        try:
            val = float(v)
            return default if (pd.isna(val) or np.isnan(val)) else val
        except (ValueError, TypeError):
            return default

    # Extract metrics
    aged_val = _to_float(row.get("Aged Value", 0.0))
    inv_val = _to_float(row.get("Inventory Value", 0.0))
    total_stock = _to_float(row.get("Total Stock", 0.0))
    unit_cost = _to_float(row.get("Unit Cost (Rs)", 0.0))
    if inv_val <= 0.0 and total_stock > 0 and unit_cost > 0:
        inv_val = total_stock * unit_cost

    avg_sales = _to_float(row.get("Avg Monthly Sales", 0.0))

    mtc_raw = row.get("Months to Clear")
    if mtc_raw == float("inf") or (isinstance(mtc_raw, str) and "inf" in str(mtc_raw).lower()):
        mtc = np.inf
    else:
        mtc = _to_float(mtc_raw, np.inf if avg_sales <= 0 else (total_stock / avg_sales if total_stock > 0 else 0.0))

    trend = str(sales_trend or row.get("Sales Trend", "Stable")).strip().title()
    turnover = (avg_sales / total_stock) if total_stock > 0 else 0.0
    risk = _to_float(row.get("Risk Score", 0.0))

    # 1. Aged Inventory Value (0-25 pts)
    if aged_val >= 25000.0:
        p_aged = 25
    elif aged_val >= 15000.0:
        p_aged = 20
    elif aged_val >= 8000.0:
        p_aged = 15
    elif aged_val >= 4000.0:
        p_aged = 10
    elif aged_val > 0.0:
        p_aged = 5
    else:
        p_aged = 0

    # 2. Total Inventory Value (0-15 pts)
    if inv_val >= 60000.0:
        p_inv = 15
    elif inv_val >= 35000.0:
        p_inv = 12
    elif inv_val >= 20000.0:
        p_inv = 8
    elif inv_val >= 10000.0:
        p_inv = 5
    elif inv_val > 0.0:
        p_inv = 2
    else:
        p_inv = 0

    # 3. Months to Clear (0-20 pts)
    if mtc >= 12.0 or np.isinf(mtc):
        p_mtc = 20
    elif mtc >= 6.0:
        p_mtc = 16
    elif mtc >= 4.5:
        p_mtc = 12
    elif mtc >= 3.0:
        p_mtc = 8
    else:
        p_mtc = 0

    # 4. Sales Trend (0-15 pts)
    # Declining demand adds urgency because clearance window is closing;
    # Growing momentum adds actionable cross-sell opportunity.
    if trend in ["Declining", "No Sales"]:
        p_trend = 15
    elif trend == "Growing":
        p_trend = 10
    elif trend == "Stable":
        p_trend = 8
    else:  # Insufficient Data or unknown
        p_trend = 5

    # 5. Sales Velocity / Turnover Rate (0-10 pts)
    if total_stock > 0 and avg_sales <= 0:
        p_vel = 10
    elif turnover < 0.10:
        p_vel = 10
    elif turnover < 0.20:
        p_vel = 7
    elif turnover < 0.33:
        p_vel = 4
    else:
        p_vel = 1

    # 6. Risk Score Alignment (0-15 pts)
    if risk >= 80.0:
        p_risk = 15
    elif risk >= 60.0:
        p_risk = 11
    elif risk >= 45.0:
        p_risk = 7
    elif risk >= 30.0:
        p_risk = 4
    else:
        p_risk = 0

    total_score = p_aged + p_inv + p_mtc + p_trend + p_vel + p_risk
    total_score = int(round(min(100, max(0, total_score))))

    if config is None:
        config = get_default_config()

    # Priority Level
    if total_score >= config.priority_critical_threshold:
        level = "Critical"
    elif total_score >= config.priority_high_threshold:
        level = "High"
    elif total_score >= config.priority_medium_threshold:
        level = "Medium"
    else:
        level = "Low"

    # Deterministic "Why Priority?" Explanation
    # Matches user format: "High priority because the item has ₹XX aged inventory, 7.2 months to clear and declining sales."
    mtc_str = "infinite (stagnant)" if np.isinf(mtc) else f"{mtc:.1f}"

    trend_phrases = {
        "Declining": "declining sales",
        "Growing": "growing sales momentum",
        "Stable": "stable sales velocity",
        "No Sales": "zero historical sales",
        "Insufficient Data": "limited historical trend data",
    }
    trend_desc = trend_phrases.get(trend, f"{trend.lower()} sales")

    why_priority = (
        f"{level} priority because the item has ₹{aged_val:,.0f} aged inventory, "
        f"{mtc_str} months to clear and {trend_desc}."
    )

    return {
        "priority_score": total_score,
        "priority_level": level,
        "why_priority": why_priority,
        "points_breakdown": {
            "aged_value_pts": p_aged,
            "inventory_value_pts": p_inv,
            "months_to_clear_pts": p_mtc,
            "sales_trend_pts": p_trend,
            "sales_velocity_pts": p_vel,
            "risk_score_pts": p_risk,
        },
    }


def calculate_sales_priority(items_df, sales_trends=None, config=None):
    """
    Enriches an items DataFrame with deterministic Sales Priority metrics:
      - 'Priority Score': int (0-100)
      - 'Priority Level': 'Critical' | 'High' | 'Medium' | 'Low'
      - 'Why Priority': Natural explanation sentence
      - 'Priority Rank': Integer rank (1 to N) specifically for Push items

    Does NOT replace or alter the original R5 Push/No Action/Red List classification.
    """
    df = items_df.copy()
    if df.empty:
        df["Priority Score"] = []
        df["Priority Level"] = []
        df["Why Priority"] = []
        df["Priority Rank"] = []
        return df

    scores = []
    levels = []
    whys = []

    for _, row in df.iterrows():
        sku = str(row.get("SKU", "")).strip().upper()
        s_trend = None
        if sales_trends and "trends_by_sku" in sales_trends:
            s_trend = sales_trends["trends_by_sku"].get(sku, {}).get("sales_trend")

        res = calculate_sales_priority_row(row, sales_trend=s_trend, config=config)
        scores.append(res["priority_score"])
        levels.append(res["priority_level"])
        whys.append(res["why_priority"])

    df["Priority Score"] = scores
    df["Priority Level"] = levels
    df["Why Priority"] = whys

    # Compute Priority Rank strictly among Push items (highest Priority Score first, Aged Value as tie-breaker)
    df["Priority Rank"] = np.nan
    push_mask = df["Class"] == "Push"
    if push_mask.any():
        push_indices = df[push_mask].sort_values(
            by=["Priority Score", "Aged Value"],
            ascending=[False, False]
        ).index
        ranks = {idx: rank for rank, idx in enumerate(push_indices, start=1)}
        df["Priority Rank"] = df.index.map(ranks)

    return df


def get_ranked_push_table(items_df, sales_trends=None, config=None):
    """
    Constructs the ranked Push SKU table requested for sales teams:
      - Rank (1, 2, 3...)
      - SKU
      - Description (Item Name)
      - Category
      - Aged Value
      - Months to Clear
      - Sales Trend
      - Risk Score
      - Priority Score
      - Recommended Action

    Additional supporting metadata:
      - Priority Level
      - Why Priority?

    Strictly preserves Push classification and orders by Priority Score descending.
    """
    if items_df is None or items_df.empty:
        return pd.DataFrame()

    df = items_df[items_df["Class"] == "Push"].copy()
    if df.empty:
        return pd.DataFrame()

    if "Priority Score" not in df.columns:
        df = calculate_sales_priority(df, sales_trends=sales_trends, config=config)

    # Sort strictly by Priority Score descending, Aged Value descending as tie-breaker
    df = df.sort_values(
        by=["Priority Score", "Aged Value"],
        ascending=[False, False]
    ).reset_index(drop=True)

    df["Rank"] = range(1, len(df) + 1)
    df["Description"] = df.get("Item Name", "")

    required_cols = [
        "Rank", "SKU", "Description", "Category",
        "Aged Value", "Months to Clear", "Sales Trend",
        "Risk Score", "Priority Score", "Priority Level",
        "Why Priority", "Recommended Action"
    ]
    avail_cols = [c for c in required_cols if c in df.columns]
    return df[avail_cols].copy()
