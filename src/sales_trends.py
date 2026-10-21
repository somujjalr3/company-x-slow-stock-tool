"""
Sales Trend Analysis Module for Company X Slow Stock Action Tool.

Uses available Sales_Lines data to compute monthly sales trends per SKU.
Calculates:
  - Monthly sales quantity
  - Monthly sales value
  - Average monthly sales (quantity & value)
  - Latest month sales (quantity & value)
  - Previous month sales (quantity & value)
  - Sales growth/decline where sufficient historical data exists

Classifies each SKU into one of five deterministic categories:
  1. Growing: Significant positive month-over-month sales growth (> +5.0%)
  2. Stable: Month-over-month sales change within stable deadband ([-5.0%, +5.0%])
  3. Declining: Significant negative month-over-month sales decline (< -5.0%) or drop to zero
  4. No Sales: Zero historical sales recorded across all periods
  5. Insufficient Data: Historical periods are unavailable or fewer than 2 months exist

CRITICAL ARCHITECTURAL CONSTRAINTS:
  - Do not fabricate data where historical periods are unavailable.
  - Used as an additional decision-support metric only.
  - Does NOT modify R1-R7 classification.
  - Clearly distinguishes CASE CLASSIFICATION from SALES TREND.
  - 100% deterministic, explainable Python logic. Never uses AI.
"""

import warnings
from typing import Dict, List, Tuple, Any, Optional
import numpy as np
import pandas as pd
from src.logger import get_logger

logger = get_logger("SalesTrends")


def parse_and_sort_months(month_series):
    """
    Chronologically sorts unique month identifiers from a Series or list of months.
    Safely parses diverse formats (e.g., 'Apr-2026', '2026-06', '2026-04-01', datetime objects).

    Returns:
      tuple of (ordered_month_labels, month_to_datetime_dict)
    """
    if month_series is None:
        return [], {}

    raw_unique = pd.Series(month_series).dropna().unique().tolist()
    if not raw_unique:
        return [], {}

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        dts = pd.to_datetime(raw_unique, errors="coerce")

    records = []
    for raw, dt in zip(raw_unique, dts):
        records.append({"raw": raw, "dt": dt})

    df = pd.DataFrame(records)
    # If all or most parsed successfully, sort by dt; fallback to string sort
    if df["dt"].notna().sum() >= max(1, len(df) // 2):
        df_valid = df[df["dt"].notna()].sort_values("dt")
        df_invalid = df[df["dt"].isna()]
        ordered = df_valid["raw"].tolist() + df_invalid["raw"].tolist()
        dt_map = {row["raw"]: row["dt"] for _, row in df.iterrows()}
    else:
        ordered = sorted(raw_unique, key=lambda x: str(x))
        dt_map = {m: None for m in ordered}

    return ordered, dt_map


def calculate_monthly_sales_trends(sales_lines, items=None, switch_map=None, stable_threshold_pct=5.0):
    """
    Computes monthly sales trends per SKU using available Sales_Lines data.

    Parameters:
      - sales_lines: DataFrame containing sales lines (supports columns: SKU, Month, Qty, Value (Rs)).
      - items: Optional DataFrame of catalog items (e.g. analysis_items or item_master).
               When provided, ensures all catalog SKUs are present in the output,
               even if they have zero recorded sales lines.
      - switch_map: Optional dict mapping old SKUs to consolidated new SKUs (Rule R3).
      - stable_threshold_pct: Float percentage threshold for 'Stable' classification (default +/- 5.0%).

    Returns a dict containing:
      - 'trends_by_sku': Dict mapping SKU -> trend metrics dictionary
      - 'summary_df': DataFrame with one row per SKU and all calculated metrics
      - 'monthly_qty_df': DataFrame pivot of SKU x Month (Quantity)
      - 'monthly_val_df': DataFrame pivot of SKU x Month (Value Rs)
      - 'ordered_months': List of month labels in chronological order
      - 'period_count': Total number of available historical months
      - 'distribution': Dict counting SKUs in each of the 5 trend classifications
    """
    empty_dist = {
        "Growing": 0,
        "Stable": 0,
        "Declining": 0,
        "No Sales": 0,
        "Insufficient Data": 0,
    }

    if sales_lines is None or not isinstance(sales_lines, pd.DataFrame) or sales_lines.empty:
        # No sales data provided
        sku_list = []
        if items is not None and isinstance(items, pd.DataFrame) and "SKU" in items.columns:
            sku_list = items["SKU"].dropna().astype(str).str.strip().str.upper().unique().tolist()

        trends = {}
        summary_rows = []
        for s in sku_list:
            trends[s] = {
                "sku": s,
                "SKU": s,
                "sales_trend": "No Sales",
                "trend_reason": "Zero sales records found in Sales_Lines.",
                "monthly_qty": {},
                "monthly_val": {},
                "total_qty": 0.0,
                "total_val": 0.0,
                "avg_monthly_qty": 0.0,
                "avg_monthly_val": 0.0,
                "latest_month": None,
                "latest_qty": 0.0,
                "latest_val": 0.0,
                "prev_month": None,
                "prev_qty": None,
                "prev_val": None,
                "growth_qty": None,
                "growth_val": None,
                "growth_pct": None,
                "sufficient_data": False,
            }
            summary_rows.append({
                "SKU": s,
                "Sales Trend": "No Sales",
                "Sales Trend Reason": "Zero sales records found in Sales_Lines.",
                "Latest Month": None,
                "Latest Month Qty": 0.0,
                "Latest Month Val": 0.0,
                "Previous Month": None,
                "Previous Month Qty": None,
                "Previous Month Val": None,
                "Sales Growth Qty": None,
                "Sales Growth Val": None,
                "Sales Growth %": None,
                "Avg Monthly Qty": 0.0,
                "Avg Monthly Val": 0.0,
                "Total Sales Qty": 0.0,
                "Total Sales Val": 0.0,
                "Sufficient Data": False,
            })

        dist = empty_dist.copy()
        dist["No Sales"] = len(sku_list)
        return {
            "trends_by_sku": trends,
            "summary_df": pd.DataFrame(summary_rows),
            "monthly_qty_df": pd.DataFrame(),
            "monthly_val_df": pd.DataFrame(),
            "ordered_months": [],
            "period_count": 0,
            "distribution": dist,
        }

    sl = sales_lines.copy()
    if "SKU" not in sl.columns:
        raise ValueError("Sales_Lines DataFrame must contain a 'SKU' column.")

    # Apply SWITCH consolidation (Rule R3)
    sl["Analysis_SKU"] = sl["SKU"].astype(str).str.strip().str.upper()
    if switch_map:
        sl["Analysis_SKU"] = sl["Analysis_SKU"].replace(switch_map)

    # Clean numeric columns
    sl["Qty"] = pd.to_numeric(sl.get("Qty", 0), errors="coerce").fillna(0)
    if "Value (Rs)" in sl.columns:
        sl["Value (Rs)"] = pd.to_numeric(sl["Value (Rs)"], errors="coerce").fillna(0)
    else:
        sl["Value (Rs)"] = 0.0

    # Ensure Month column exists
    if "Month" not in sl.columns:
        sl["Month"] = "Period_1"

    ordered_months, _ = parse_and_sort_months(sl["Month"])
    period_count = len(ordered_months)

    # Build monthly pivots
    pvt_qty = sl.pivot_table(
        index="Analysis_SKU",
        columns="Month",
        values="Qty",
        aggfunc="sum",
        fill_value=0.0
    )
    pvt_val = sl.pivot_table(
        index="Analysis_SKU",
        columns="Month",
        values="Value (Rs)",
        aggfunc="sum",
        fill_value=0.0
    )

    # Reorder columns chronologically
    avail_ordered = [m for m in ordered_months if m in pvt_qty.columns]
    pvt_qty = pvt_qty.reindex(columns=avail_ordered, fill_value=0.0)
    pvt_val = pvt_val.reindex(columns=avail_ordered, fill_value=0.0)

    # Determine master SKU list
    if items is not None and isinstance(items, pd.DataFrame) and "SKU" in items.columns:
        master_skus = items["SKU"].dropna().astype(str).str.strip().str.upper().unique().tolist()
    else:
        master_skus = pvt_qty.index.tolist()

    trends_by_sku = {}
    distribution = empty_dist.copy()

    has_sufficient_history = period_count >= 2
    latest_month_label = ordered_months[-1] if ordered_months else None
    prev_month_label = ordered_months[-2] if period_count >= 2 else None

    for sku in master_skus:
        has_record = sku in pvt_qty.index
        if has_record:
            sku_qty_series = pvt_qty.loc[sku]
            sku_val_series = pvt_val.loc[sku]
            m_qty = {m: float(sku_qty_series.get(m, 0.0)) for m in avail_ordered}
            m_val = {m: float(sku_val_series.get(m, 0.0)) for m in avail_ordered}
            total_qty = float(sku_qty_series.sum())
            total_val = float(sku_val_series.sum())
        else:
            m_qty = {m: 0.0 for m in avail_ordered}
            m_val = {m: 0.0 for m in avail_ordered}
            total_qty = 0.0
            total_val = 0.0

        avg_monthly_qty = (total_qty / period_count) if period_count > 0 else 0.0
        avg_monthly_val = (total_val / period_count) if period_count > 0 else 0.0

        # Classification logic
        if total_qty == 0.0:
            sales_trend = "No Sales"
            trend_reason = "Zero historical sales units recorded across all observation periods."
            latest_qty = 0.0 if period_count >= 1 else None
            latest_val = 0.0 if period_count >= 1 else None
            prev_qty = 0.0 if has_sufficient_history else None
            prev_val = 0.0 if has_sufficient_history else None
            growth_qty = 0.0 if has_sufficient_history else None
            growth_val = 0.0 if has_sufficient_history else None
            growth_pct = 0.0 if has_sufficient_history else None
            sufficient_data = has_sufficient_history

        elif not has_sufficient_history:
            # Historical periods unavailable or < 2 months
            # "Do not fabricate data where historical periods are unavailable."
            sales_trend = "Insufficient Data"
            trend_reason = (
                f"Only {period_count} historical sales period is available ({latest_month_label}); "
                "a minimum of 2 chronological months is required to compute trend without fabricating data."
            )
            latest_qty = m_qty.get(latest_month_label, 0.0) if latest_month_label else None
            latest_val = m_val.get(latest_month_label, 0.0) if latest_month_label else None
            prev_qty = None
            prev_val = None
            growth_qty = None
            growth_val = None
            growth_pct = None
            sufficient_data = False

        else:
            # Sufficient data (at least 2 chronological months and total_qty > 0)
            sufficient_data = True
            latest_qty = float(m_qty.get(latest_month_label, 0.0))
            latest_val = float(m_val.get(latest_month_label, 0.0))
            prev_qty = float(m_qty.get(prev_month_label, 0.0))
            prev_val = float(m_val.get(prev_month_label, 0.0))

            growth_qty = latest_qty - prev_qty
            growth_val = latest_val - prev_val

            if prev_qty <= 0.0:
                if latest_qty > 0.0:
                    # Emerged from zero sales
                    sales_trend = "Growing"
                    growth_pct = 100.0
                    trend_reason = (
                        f"Sales increased from {prev_qty:,.0f} units in {prev_month_label} to {latest_qty:,.0f} units "
                        f"(₹{latest_val:,.0f}) in {latest_month_label}."
                    )
                else:
                    # Both periods at or below zero sales
                    sales_trend = "Declining"
                    growth_pct = 0.0
                    trend_reason = (
                        f"Sales dropped to or remained at 0 units in both {prev_month_label} and {latest_month_label} "
                        f"despite {total_qty:,.0f} units recorded in earlier months."
                    )

            elif latest_qty <= 0.0:
                # Dropped to zero or below
                sales_trend = "Declining"
                growth_pct = -100.0
                trend_reason = (
                    f"Sales dropped from {prev_qty:,.0f} units in {prev_month_label} to {latest_qty:,.0f} units in {latest_month_label} "
                    "(-100.0% decline)."
                )

            else:
                # Both prev_qty > 0 and latest_qty > 0
                pct = (growth_qty / prev_qty) * 100.0
                growth_pct = float(pct)

                if pct > stable_threshold_pct:
                    sales_trend = "Growing"
                    trend_reason = (
                        f"Latest month sales ({latest_qty:,.0f} units in {latest_month_label}) grew by +{pct:.1f}% "
                        f"over previous month ({prev_qty:,.0f} units in {prev_month_label})."
                    )
                elif pct < -stable_threshold_pct:
                    sales_trend = "Declining"
                    trend_reason = (
                        f"Latest month sales ({latest_qty:,.0f} units in {latest_month_label}) declined by {pct:.1f}% "
                        f"compared to previous month ({prev_qty:,.0f} units in {prev_month_label})."
                    )
                else:
                    sales_trend = "Stable"
                    sign = "+" if pct >= 0 else ""
                    trend_reason = (
                        f"Month-over-month sales velocity remains stable at {sign}{pct:.1f}% "
                        f"({latest_qty:,.0f} units in {latest_month_label} vs {prev_qty:,.0f} units in {prev_month_label})."
                    )

        distribution[sales_trend] = distribution.get(sales_trend, 0) + 1

        trends_by_sku[sku] = {
            "sku": sku,
            "sales_trend": sales_trend,
            "trend_reason": trend_reason,
            "monthly_qty": m_qty,
            "monthly_val": m_val,
            "total_qty": total_qty,
            "total_val": total_val,
            "avg_monthly_qty": avg_monthly_qty,
            "avg_monthly_val": avg_monthly_val,
            "latest_month": latest_month_label,
            "latest_qty": latest_qty,
            "latest_val": latest_val,
            "prev_month": prev_month_label,
            "prev_qty": prev_qty,
            "prev_val": prev_val,
            "growth_qty": growth_qty,
            "growth_val": growth_val,
            "growth_pct": growth_pct,
            "sufficient_data": sufficient_data,
        }

    summary_rows = []
    for s, data in trends_by_sku.items():
        summary_rows.append({
            "SKU": s,
            "Sales Trend": data["sales_trend"],
            "Sales Trend Reason": data["trend_reason"],
            "Latest Month": data["latest_month"],
            "Latest Month Qty": data["latest_qty"],
            "Latest Month Val": data["latest_val"],
            "Previous Month": data["prev_month"],
            "Previous Month Qty": data["prev_qty"],
            "Previous Month Val": data["prev_val"],
            "Sales Growth Qty": data["growth_qty"],
            "Sales Growth Val": data["growth_val"],
            "Sales Growth %": data["growth_pct"],
            "Avg Monthly Qty": data["avg_monthly_qty"],
            "Avg Monthly Val": data["avg_monthly_val"],
            "Total Sales Qty": data["total_qty"],
            "Total Sales Val": data["total_val"],
            "Sufficient Data": data["sufficient_data"],
        })

    summary_df = pd.DataFrame(summary_rows)

    return {
        "trends_by_sku": trends_by_sku,
        "summary_df": summary_df,
        "monthly_qty_df": pvt_qty,
        "monthly_val_df": pvt_val,
        "ordered_months": avail_ordered,
        "period_count": period_count,
        "distribution": distribution,
    }


def get_top_declining_push_items(summary_df, items_df, top_n=5):
    """
    Identifies top Push items with the sharpest sales decline.

    Ranks Push items where Sales Trend == 'Declining' (or negative growth %):
      1. Primary rank: Sales Growth % ascending (most negative % first)
      2. Secondary rank: Aged Value descending (highest capital at risk)

    Returns DataFrame of top declining Push SKUs.
    """
    if summary_df is None or items_df is None or summary_df.empty or items_df.empty:
        return pd.DataFrame()

    push_skus = items_df[items_df["Class"] == "Push"]["SKU"].tolist()
    merged = summary_df[summary_df["SKU"].isin(push_skus)].copy()

    # Join with item details
    cols_to_join = ["SKU", "Item Name", "Category", "Class", "Aged Value", "Months to Clear", "Total Stock", "Unit Cost (Rs)"]
    avail_cols = [c for c in cols_to_join if c in items_df.columns]
    merged = merged.merge(items_df[avail_cols], on="SKU", how="left")

    # Filter for declining or negative growth
    declining = merged[
        (merged["Sales Trend"] == "Declining") |
        (merged["Sales Growth %"].notna() & (merged["Sales Growth %"] < 0))
    ].copy()

    if declining.empty:
        return pd.DataFrame()

    declining = declining.sort_values(
        by=["Sales Growth %", "Aged Value"],
        ascending=[True, False]
    ).head(top_n).reset_index(drop=True)

    return declining


def get_top_growing_push_items(summary_df, items_df, top_n=5):
    """
    Identifies top Push items with positive sales growth.

    Ranks Push items where Sales Trend == 'Growing' (or positive growth %):
      1. Primary rank: Sales Growth % descending (highest positive growth first)
      2. Secondary rank: Aged Value descending

    Returns DataFrame of top growing Push SKUs.
    """
    if summary_df is None or items_df is None or summary_df.empty or items_df.empty:
        return pd.DataFrame()

    push_skus = items_df[items_df["Class"] == "Push"]["SKU"].tolist()
    merged = summary_df[summary_df["SKU"].isin(push_skus)].copy()

    # Join with item details
    cols_to_join = ["SKU", "Item Name", "Category", "Class", "Aged Value", "Months to Clear", "Total Stock", "Unit Cost (Rs)"]
    avail_cols = [c for c in cols_to_join if c in items_df.columns]
    merged = merged.merge(items_df[avail_cols], on="SKU", how="left")

    # Filter for growing or positive growth
    growing = merged[
        (merged["Sales Trend"] == "Growing") |
        (merged["Sales Growth %"].notna() & (merged["Sales Growth %"] > 0))
    ].copy()

    if growing.empty:
        return pd.DataFrame()

    growing = growing.sort_values(
        by=["Sales Growth %", "Aged Value"],
        ascending=[False, False]
    ).head(top_n).reset_index(drop=True)

    return growing
