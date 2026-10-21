import re
from typing import Dict, List, Tuple, Any, Optional
import warnings
import numpy as np
import pandas as pd
from src.logger import get_logger

logger = get_logger("BusinessLogic")

from src.sales_trends import (
    calculate_monthly_sales_trends,
    get_top_declining_push_items,
    get_top_growing_push_items,
)
from src.sales_priority import (
    calculate_sales_priority,
    calculate_sales_priority_row,
    get_ranked_push_table,
)
from src.dead_stock import (
    identify_dead_stock,
    get_dead_stock_summary,
)
from src.config import (
    CaseConfig,
    get_default_config,
)



def _normalise_text(series):
    """Trim whitespace and convert text series to uppercase."""
    return series.astype(str).str.strip().str.upper()


def _clean_name(val):
    """Normalize whitespace and uppercase an item name for reliable matching."""
    if pd.isna(val):
        return ""
    text = str(val).strip()
    return re.sub(r"\s+", " ", text).upper()


def build_switch_map(item_master):
    """
    R3 PACK-SIZE SWITCH:
    If Alternate Flag = SWITCH:
      - identify the old SKU
      - identify the new SKU using Alternate Item (name) matching Item Name
      - consolidate historical sales and stock under the new SKU
      - the old SKU must not remain as a separate analytical item
      - the final reporting SKU must be the new SKU
      - preserve a clear switch mapping for auditability

    Items with an alternate item name are NOT consolidated unless
    Alternate Flag is explicitly 'SWITCH'.
    """
    im = item_master.copy()
    im["SKU"] = _normalise_text(im["SKU"])
    im["Alternate Flag"] = im["Alternate Flag"].astype(str).str.strip().str.upper()
    im["Clean_Item_Name"] = im["Item Name"].apply(_clean_name)
    im["Clean_Alt_Name"] = im["Alternate Item (name)"].apply(_clean_name)

    # Name to SKU lookup based on normalized item names
    name_to_sku = (
        im.drop_duplicates("Clean_Item_Name")
          .set_index("Clean_Item_Name")["SKU"]
          .to_dict()
    )
    sku_to_name = im.set_index("SKU")["Item Name"].to_dict()

    # Only rows where Alternate Flag is explicitly SWITCH
    switch_rows = im[im["Alternate Flag"] == "SWITCH"].copy()

    direct_map = {}
    records = []

    for _, row in switch_rows.iterrows():
        old_sku = row["SKU"]
        alt_clean = row["Clean_Alt_Name"]
        new_sku = name_to_sku.get(alt_clean)

        if new_sku and new_sku != old_sku:
            direct_map[old_sku] = new_sku
            records.append({
                "Old SKU": old_sku,
                "Old Item Name": row["Item Name"],
                "New SKU": new_sku,
                "New Item Name": sku_to_name.get(new_sku, ""),
                "Alternate Item (name)": row["Alternate Item (name)"],
                "Status": "Applied",
            })
        else:
            records.append({
                "Old SKU": old_sku,
                "Old Item Name": row["Item Name"],
                "New SKU": new_sku or "",
                "New Item Name": sku_to_name.get(new_sku, "") if new_sku else "",
                "Alternate Item (name)": row["Alternate Item (name)"],
                "Status": "Not resolved",
            })

    # Transitive chain resolution: if A -> B and B -> C, resolve A -> C
    final_mapping = {}
    for old_sku in direct_map:
        target = direct_map[old_sku]
        visited = {old_sku}
        while target in direct_map and target not in visited:
            visited.add(target)
            target = direct_map[target]
        final_mapping[old_sku] = target

    # Update audit records with final target if chain resolved
    for rec in records:
        if rec["Status"] == "Applied":
            final_target = final_mapping.get(rec["Old SKU"], rec["New SKU"])
            rec["New SKU"] = final_target
            rec["New Item Name"] = sku_to_name.get(final_target, rec["New Item Name"])

    audit_df = pd.DataFrame(records)
    return final_mapping, audit_df


def calculate_inventory_risk_row(row, config=None):
    """
    Deterministic scoring of a single SKU across 5 operational risk dimensions:
      1. Aged Stock Percentage (0-25 pts): % of physical inventory aged 91+ days
      2. Months to Clear (0-25 pts): estimated months required to clear stock
      3. Sales Velocity (0-20 pts): monthly turnover rate (Avg Monthly Sales / Total Stock)
      4. 6M Sales Volume Scale (0-15 pts): demand scale vs Master Pack batch packaging
      5. Aged Inventory Value (0-15 pts): financial capital trapped in aged inventory

    Risk Levels:
      Configurable via CaseConfig. Default:
      - 0-29:   Low
      - 30-59:  Medium
      - 60-79:  High
      - 80-100: Critical
    """
    total_stock = float(row.get("Total Stock", 0) or 0)
    aged_qty = float(row.get("Aged Qty", 0) or 0)
    aged_value = float(row.get("Aged Value", 0) or 0)
    sales_qty = float(row.get("6M Sales Qty", 0) or 0)
    avg_sales = float(row.get("Avg Monthly Sales", 0) or 0)
    mtc_val = row.get("Months to Clear")
    if mtc_val == float("inf") or (isinstance(mtc_val, str) and "inf" in str(mtc_val).lower()) or str(mtc_val).strip() == "∞":
        mtc = np.inf
    else:
        try:
            mtc = float(mtc_val or 0)
        except (ValueError, TypeError):
            mtc = np.inf
    master_pack = float(row.get("Master Pack Qty", 1) or 1)
    if master_pack <= 0 or np.isnan(master_pack):
        master_pack = 1.0

    # 1. Aged Stock Percentage (0-25 pts)
    aged_pct = (aged_qty / total_stock * 100.0) if total_stock > 0 else 0.0
    if aged_pct >= 60.0:
        p_aged = 25
        d_aged = f"{aged_pct:.0f}% of inventory is aged"
    elif aged_pct >= 40.0:
        p_aged = 20
        d_aged = f"{aged_pct:.0f}% of inventory is aged"
    elif aged_pct >= 25.0:
        p_aged = 15
        d_aged = f"{aged_pct:.0f}% of inventory is aged"
    elif aged_pct >= 10.0:
        p_aged = 8
        d_aged = f"{aged_pct:.0f}% aged stock"
    elif aged_pct > 0.0:
        p_aged = 4
        d_aged = f"{aged_pct:.1f}% aged stock"
    else:
        p_aged = 0
        d_aged = "zero aged stock"

    # 2. Months to Clear (0-25 pts)
    if total_stock <= 0:
        p_mtc = 0
        d_mtc = "zero warehouse inventory"
    elif np.isinf(mtc) or avg_sales <= 0:
        p_mtc = 25
        d_mtc = "the inventory is non-clearing (zero sales rate)"
    elif mtc >= 12.0:
        p_mtc = 22
        d_mtc = f"the inventory will take {mtc:.1f} months to clear"
    elif mtc >= 6.0:
        p_mtc = 18
        d_mtc = f"the inventory will take {mtc:.1f} months to clear"
    elif mtc >= 3.0:
        p_mtc = 12
        d_mtc = f"the inventory will take {mtc:.1f} months to clear"
    elif mtc >= 1.5:
        p_mtc = 5
        d_mtc = f"clearance runway is {mtc:.1f} months"
    else:
        p_mtc = 0
        d_mtc = "rapid clearance runway"

    # 3. Sales Velocity (0-20 pts)
    turnover = (avg_sales / total_stock) if total_stock > 0 else 0.0
    if total_stock > 0 and avg_sales <= 0:
        p_vel = 20
        d_vel = "monthly sales velocity is zero"
    elif turnover < 0.10 and total_stock > 0:
        p_vel = 16
        d_vel = "monthly sales velocity is very low"
    elif turnover < 0.20 and total_stock > 0:
        p_vel = 12
        d_vel = "monthly sales velocity is low"
    elif turnover < 0.33 and total_stock > 0:
        p_vel = 6
        d_vel = "monthly sales velocity is moderate"
    else:
        p_vel = 0
        d_vel = "healthy sales velocity"

    # 4. 6M Sales Demand / Volume Scale (0-15 pts)
    if sales_qty <= 0:
        p_vol = 15
        d_vol = "zero sales demand over 6 months"
    elif sales_qty < master_pack:
        p_vol = 12
        d_vol = f"6M sales ({sales_qty:,.0f}) below 1 Master Pack ({master_pack:,.0f})"
    elif sales_qty < 2 * master_pack:
        p_vol = 7
        d_vol = f"6M sales volume is weak ({sales_qty:,.0f} units)"
    elif sales_qty < 5 * master_pack:
        p_vol = 3
        d_vol = "moderate commercial volume"
    else:
        p_vol = 0
        d_vol = "strong commercial volume"

    # 5. Aged Inventory Value (0-15 pts)
    if aged_value >= 25000:
        p_val = 15
        d_val = f"₹{aged_value:,.0f} tied up in aged stock"
    elif aged_value >= 15000:
        p_val = 12
        d_val = f"₹{aged_value:,.0f} tied up in aged stock"
    elif aged_value >= 7500:
        p_val = 8
        d_val = f"₹{aged_value:,.0f} tied up in aged stock"
    elif aged_value >= 2500:
        p_val = 4
        d_val = f"₹{aged_value:,.0f} aged value"
    elif aged_value > 0:
        p_val = 2
        d_val = f"₹{aged_value:,.0f} aged value"
    else:
        p_val = 0
        d_val = "zero aged capital at risk"

    total_score = p_aged + p_mtc + p_vel + p_vol + p_val
    total_score = int(round(min(100, max(0, total_score))))

    if config is None:
        config = get_default_config()

    if total_score >= config.risk_critical_threshold:
        level = "Critical"
    elif total_score >= config.risk_high_threshold:
        level = "High"
    elif total_score >= config.risk_medium_threshold:
        level = "Medium"
    else:
        level = "Low"

    # Identify significant contributing factors in natural narrative order
    significant_drivers = []
    if p_aged >= 8:
        significant_drivers.append(d_aged)
    if p_vel >= 12:
        significant_drivers.append(d_vel)
    if p_mtc >= 12:
        significant_drivers.append(d_mtc)
    if p_vol >= 7:
        significant_drivers.append(d_vol)
    if p_val >= 8:
        significant_drivers.append(d_val)

    all_drivers = [d_aged, d_vel, d_mtc, d_vol, d_val]

    if not significant_drivers:
        explanation = "Low risk with healthy sales velocity, zero aged stock and rapid clearance."
    else:
        top_factors = significant_drivers[:3]
        if len(top_factors) == 1:
            fact_str = top_factors[0]
        elif len(top_factors) == 2:
            fact_str = f"{top_factors[0]} and {top_factors[1]}"
        else:
            fact_str = f"{top_factors[0]}, {top_factors[1]} and {top_factors[2]}"

        if level in ["Critical", "High"]:
            explanation = f"{level} risk because {fact_str}."
        elif level == "Medium":
            explanation = f"Medium risk because {fact_str}."
        else:
            explanation = f"Low risk with {fact_str}."

    return {
        "Risk Score": total_score,
        "Risk Level": level,
        "Risk Drivers": "; ".join(all_drivers),
        "Risk Explanation": explanation,
        "Risk Pts Aged": p_aged,
        "Risk Pts MTC": p_mtc,
        "Risk Pts Velocity": p_vel,
        "Risk Pts Volume": p_vol,
        "Risk Pts Value": p_val,
    }


def calculate_inventory_risk(data, config=None):
    """
    Reusable deterministic Inventory Risk Scoring Engine (0-100).
    Never uses AI. Evaluates 5 operational inventory risk dimensions:
      1. Aged Stock Percentage (0-25 pts)
      2. Months to Clear (0-25 pts)
      3. Sales Velocity (0-20 pts)
      4. 6M Sales Volume Scale (0-15 pts)
      5. Aged Inventory Value (0-15 pts)

    Risk Levels:
      Configurable via CaseConfig. Default:
      0-29:   Low
      30-59:  Medium
      60-79:  High
      80-100: Critical

    Accepts a pandas DataFrame, pandas Series, or dictionary.
    Does NOT modify or override R1-R7 slow stock classifications.
    """
    if isinstance(data, pd.DataFrame):
        df = data.copy()
        if df.empty:
            for col in [
                "Risk Score", "Risk Level", "Risk Drivers", "Risk Explanation",
                "Risk Pts Aged", "Risk Pts MTC", "Risk Pts Velocity", "Risk Pts Volume", "Risk Pts Value"
            ]:
                df[col] = []
            return df
        results = [calculate_inventory_risk_row(row, config=config) for _, row in df.iterrows()]
        res_df = pd.DataFrame(results, index=df.index)
        for col in res_df.columns:
            df[col] = res_df[col]
        return df
    elif isinstance(data, (pd.Series, dict)):
        return calculate_inventory_risk_row(data, config=config)
    else:
        raise TypeError("calculate_inventory_risk expects a pandas DataFrame, Series, or dictionary")


def calculate_working_capital_impact(items):
    """
    Computes Working Capital Impact and Cash at Risk metrics across active catalog items:
      - Total Inventory Value = Total Stock * Unit Cost
      - Aged Inventory Value = Aged Qty * Unit Cost
      - Aged Inventory % = Aged Inventory Value / Total Inventory Value
      - Push Inventory Value = Inventory Value for Push items
      - Red List Inventory Value = Inventory Value for Red List items
      - No Action Inventory Value = Inventory Value for No Action items
      - Number of high-risk SKUs = Count of SKUs with Risk Level in ['Critical', 'High']

    Cash at Risk Concept:
      Aged Inventory Value represents capital tied up in aged stock (91+ days),
      not guaranteed cash recovery.
    """
    df = items.copy()
    if df.empty:
        summary = {
            "total_inventory_value": 0.0,
            "aged_inventory_value": 0.0,
            "cash_at_risk": 0.0,
            "aged_inventory_pct": 0.0,
            "push_inventory_value": 0.0,
            "red_list_inventory_value": 0.0,
            "no_action_inventory_value": 0.0,
            "push_aged_value": 0.0,
            "red_list_aged_value": 0.0,
            "no_action_aged_value": 0.0,
            "high_risk_sku_count": 0,
            "total_skus": 0,
            "cash_at_risk_note": "Inventory value tied up in aged stock, not guaranteed cash recovery.",
        }
        return {
            "summary": summary,
            "by_class": pd.DataFrame(columns=["Class", "Inventory Value", "Aged Value", "SKU Count", "Aged Share %"]),
            "by_category": pd.DataFrame(columns=["Category", "Inventory Value", "Aged Value", "SKU Count", "Aged Share %"]),
            "top10_aged_skus": pd.DataFrame(),
        }

    if "Inventory Value" not in df.columns:
        unit_cost = pd.to_numeric(df.get("Unit Cost (Rs)", 0), errors="coerce").fillna(0)
        total_stock = pd.to_numeric(df.get("Total Stock", 0), errors="coerce").fillna(0)
        df["Inventory Value"] = total_stock * unit_cost

    if "Aged Value" not in df.columns:
        unit_cost = pd.to_numeric(df.get("Unit Cost (Rs)", 0), errors="coerce").fillna(0)
        aged_qty = pd.to_numeric(df.get("Aged Qty", 0), errors="coerce").fillna(0)
        df["Aged Value"] = aged_qty * unit_cost

    total_inventory_value = float(df["Inventory Value"].sum())
    aged_inventory_value = float(df["Aged Value"].sum())
    aged_inventory_pct = (aged_inventory_value / total_inventory_value * 100.0) if total_inventory_value > 0 else 0.0

    push_mask = df["Class"] == "Push"
    red_mask = df["Class"] == "Red List"
    noaction_mask = df["Class"] == "No Action"

    push_inventory_value = float(df.loc[push_mask, "Inventory Value"].sum())
    red_inventory_value = float(df.loc[red_mask, "Inventory Value"].sum())
    noaction_inventory_value = float(df.loc[noaction_mask, "Inventory Value"].sum())

    push_aged_value = float(df.loc[push_mask, "Aged Value"].sum())
    red_aged_value = float(df.loc[red_mask, "Aged Value"].sum())
    noaction_aged_value = float(df.loc[noaction_mask, "Aged Value"].sum())

    if "Risk Level" in df.columns:
        high_risk_sku_count = int(df["Risk Level"].isin(["Critical", "High"]).sum())
    elif "Risk Score" in df.columns:
        high_risk_sku_count = int((df["Risk Score"] >= 60).sum())
    else:
        high_risk_sku_count = 0

    push_share_of_aged = (push_aged_value / aged_inventory_value * 100.0) if aged_inventory_value > 0 else 0.0

    summary = {
        "total_inventory_value": total_inventory_value,
        "aged_inventory_value": aged_inventory_value,
        "cash_at_risk": aged_inventory_value,
        "aged_inventory_pct": aged_inventory_pct,
        "push_inventory_value": push_inventory_value,
        "red_list_inventory_value": red_inventory_value,
        "no_action_inventory_value": noaction_inventory_value,
        "push_aged_value": push_aged_value,
        "red_list_aged_value": red_aged_value,
        "no_action_aged_value": noaction_aged_value,
        "push_share_of_aged": push_share_of_aged,
        "high_risk_sku_count": high_risk_sku_count,
        "total_skus": len(df),
        "cash_at_risk_note": "Inventory value tied up in aged stock, not guaranteed cash recovery.",
    }

    # By Classification breakdown
    by_class = (
        df.groupby("Class")
        .agg(
            **{
                "Inventory Value": ("Inventory Value", "sum"),
                "Aged Value": ("Aged Value", "sum"),
                "SKU Count": ("SKU", "count"),
                "Aged Qty": ("Aged Qty", "sum"),
                "Total Stock": ("Total Stock", "sum"),
            }
        )
        .reset_index()
    )
    by_class["Aged Share %"] = np.where(
        by_class["Inventory Value"] > 0,
        by_class["Aged Value"] / by_class["Inventory Value"] * 100.0,
        0.0
    )

    # By Category breakdown
    by_category = (
        df.groupby("Category")
        .agg(
            **{
                "Inventory Value": ("Inventory Value", "sum"),
                "Aged Value": ("Aged Value", "sum"),
                "SKU Count": ("SKU", "count"),
                "Aged Qty": ("Aged Qty", "sum"),
                "Total Stock": ("Total Stock", "sum"),
            }
        )
        .reset_index()
        .sort_values("Aged Value", ascending=False)
    )
    by_category["Aged Share %"] = np.where(
        by_category["Inventory Value"] > 0,
        by_category["Aged Value"] / by_category["Inventory Value"] * 100.0,
        0.0
    )

    # Top 10 SKUs by Aged Value
    desired_cols = [
        "SKU", "Item Name", "Category", "Class",
        "Unit Cost (Rs)", "Total Stock", "Inventory Value",
        "Aged Qty", "Aged Value", "Months to Clear",
        "Risk Score", "Risk Level", "Risk Explanation",
        "Recommended Action"
    ]
    avail_top10_cols = [c for c in desired_cols if c in df.columns]
    top10_aged_skus = (
        df.sort_values("Aged Value", ascending=False)
        .head(10)[avail_top10_cols]
        .copy()
        .reset_index(drop=True)
    )

    return {
        "summary": summary,
        "by_class": by_class,
        "by_category": by_category,
        "top10_aged_skus": top10_aged_skus,
    }


def compute_sales_trends(sales_lines, switch_map=None):
    """
    Computes sales trajectory across the 6-month observation window to detect
    declining demand trends per SKU.

    Splits the observed sales period into early half vs late half (e.g. Q1 vs Q2).
    Returns dict keyed by Analysis SKU:
      {
         'declining': bool,
         'trend_pct': float,
         'early_qty': float,
         'late_qty': float,
      }
    """
    if sales_lines is None or not isinstance(sales_lines, pd.DataFrame) or sales_lines.empty:
        return {}
    if "Month" not in sales_lines.columns or "Qty" not in sales_lines.columns:
        return {}

    df = sales_lines.copy()
    if switch_map:
        df["Analysis_SKU"] = df["SKU"].astype(str).str.strip().str.upper().replace(switch_map)
    else:
        df["Analysis_SKU"] = df["SKU"].astype(str).str.strip().str.upper()

    df["Qty"] = pd.to_numeric(df["Qty"], errors="coerce").fillna(0)

    # Detect unique months in chronological order
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        df["dt"] = pd.to_datetime(df["Month"], errors="coerce")

    valid_dt = df.dropna(subset=["dt"])
    if not valid_dt.empty and len(valid_dt["dt"].unique()) >= 2:
        month_order = valid_dt[["Month", "dt"]].drop_duplicates().sort_values("dt")["Month"].tolist()
    else:
        month_order = df["Month"].dropna().unique().tolist()

    if len(month_order) < 2:
        return {}

    mid = len(month_order) // 2
    early_months = set(month_order[:mid])
    late_months = set(month_order[mid:])

    early_sales = df[df["Month"].isin(early_months)].groupby("Analysis_SKU")["Qty"].sum()
    late_sales = df[df["Month"].isin(late_months)].groupby("Analysis_SKU")["Qty"].sum()

    all_skus = set(early_sales.index).union(set(late_sales.index))
    trends = {}
    for s in all_skus:
        e = float(early_sales.get(s, 0.0))
        l = float(late_sales.get(s, 0.0))
        is_dec = bool((l < e) and (e > 0))
        pct = float(((l - e) / e * 100.0) if e > 0 else (100.0 if l > 0 else 0.0))
        trends[s] = {
            "declining": is_dec,
            "trend_pct": pct,
            "early_qty": e,
            "late_qty": l,
        }
    return trends


def recommend_operational_action(item_data, is_declining=None, sales_trend_pct=None):
    """
    Deterministic Recommended Action Engine.
    Recommends an operational action, priority, and explainable reason based on:
      - Slow Stock Classification (Red List, No Action, Push, Inactive)
      - Deterministic Risk Score & Level
      - Inventory Metrics (Aged Qty, Aged Value, Inventory Value, Months to Clear, Turnover Velocity)
      - Sales Trajectory (Declining Sales)

    Strictly adheres to Rules R1-R7 and never modifies classifications.
    Never uses AI. 100% deterministic, explainable Python logic.

    Returns dict with keys:
      - 'action': Recommended operational action
      - 'recommended_action': Alias for 'action'
      - 'priority': 'Urgent', 'High', 'Medium', or 'Low'
      - 'reason': Explainable deterministic rationale detailing specific drivers
      - 'action_reason': Alias for 'reason'
      - 'drivers': List of active operational drivers
    """
    if hasattr(item_data, "to_dict"):
        d = item_data.to_dict()
    elif isinstance(item_data, dict):
        d = item_data
    else:
        d = dict(item_data)

    sku = str(d.get("SKU", "Unknown SKU")).strip()
    cls = str(d.get("Class", "")).strip()

    def _to_float(v, default=0.0):
        try:
            val = float(v)
            return default if (pd.isna(val) or np.isnan(val)) else val
        except (ValueError, TypeError):
            return default

    sales_qty = _to_float(d.get("6M Sales Qty", 0))
    master_pack = _to_float(d.get("Master Pack Qty", 0))
    aged_qty = _to_float(d.get("Aged Qty", 0))
    aged_val = _to_float(d.get("Aged Value", 0))
    total_stock = _to_float(d.get("Total Stock", 0))
    unit_cost = _to_float(d.get("Unit Cost (Rs)", 0))
    inv_val = _to_float(d.get("Inventory Value", total_stock * unit_cost))
    avg_sales = _to_float(d.get("Avg Monthly Sales", sales_qty / 6.0))

    mtc_raw = d.get("Months to Clear")
    if mtc_raw == float("inf") or (isinstance(mtc_raw, str) and "inf" in str(mtc_raw).lower()):
        mtc = np.inf
    else:
        mtc = _to_float(mtc_raw, np.inf if avg_sales <= 0 else total_stock / avg_sales)

    # Check declining sales flag
    if is_declining is None:
        raw_dec = d.get("Declining Sales", d.get("is_declining", False))
        is_dec = bool(raw_dec) if not pd.isna(raw_dec) else False
    else:
        is_dec = bool(is_declining)

    if sales_trend_pct is None:
        raw_pct = d.get("Sales Trend %", d.get("trend_pct", 0.0))
        trend_pct = _to_float(raw_pct, 0.0)
    else:
        trend_pct = _to_float(sales_trend_pct, 0.0)

    # Operational metric thresholds for Push differentiation:
    # 1. High aged value: >= ₹15,000
    is_high_aged_val = aged_val >= 15000.0
    # 2. High months to clear: >= 6.0 months or infinite
    is_high_mtc = (mtc >= 6.0) or np.isinf(mtc)
    # 3. High inventory value: >= ₹50,000
    is_high_inv_val = inv_val >= 50000.0
    # 4. Low sales velocity: < 30 units/month or monthly turnover rate < 20%
    turnover_rate = (avg_sales / total_stock) if total_stock > 0 else 0.0
    is_low_velocity = (avg_sales < 30.0) or (turnover_rate < 0.20 and total_stock > 50)

    drivers = []

    # =========================================================================
    # 1. RED LIST RECOMMENDATIONS
    # Examples:
    # - Review item viability
    # - Consider liquidation/discontinuation
    # - Stop unnecessary replenishment
    # - Review obsolete inventory
    # =========================================================================
    if cls == "Red List":
        if sales_qty == 0:
            drivers.append("Zero 6M customer sales")
            if aged_val > 0:
                drivers.append(f"Obsolete aged inventory (₹{aged_val:,.0f})")
                drivers.append("Replenishment halt required")
                priority = "Urgent"
                action = "Review obsolete inventory & consider commercial liquidation / delisting discontinuation"
                reason = (
                    f"Zero customer sales recorded over 6 months with ₹{aged_val:,.0f} tied up in obsolete aged stock; "
                    "stop unnecessary replenishment and initiate commercial delisting or liquidation review."
                )
            else:
                drivers.append("Zero warehouse inventory")
                drivers.append("Replenishment halt required")
                priority = "Medium"
                action = "Stop unnecessary replenishment & proceed with discontinuation"
                reason = (
                    "Zero customer sales recorded over 6 months with zero warehouse inventory; formalize SKU discontinuation in catalog "
                    "and stop unnecessary replenishment."
                )
        else:
            drivers.append(f"Sales volume ({sales_qty:,.0f}) below 1 Master Pack ({master_pack:,.0f})")
            if aged_val >= 5000:
                drivers.append(f"Aged capital tied up (₹{aged_val:,.0f})")
                drivers.append("Replenishment halt required")
                priority = "High"
                action = "Review item commercial viability & stop unnecessary replenishment"
                reason = (
                    f"6-month volume ({sales_qty:,.0f} units) failed to meet 1 Master Pack ({master_pack:,.0f} units) "
                    f"with ₹{aged_val:,.0f} in aged inventory; stop unnecessary replenishment and evaluate supplier MOQ or discontinuation."
                )
            else:
                priority = "Medium"
                action = "Review item viability & consider discontinuation"
                reason = (
                    f"6-month volume ({sales_qty:,.0f} units) is below the commercial Master Pack threshold "
                    f"({master_pack:,.0f} units); review commercial viability with category team before replenishment."
                )

    # =========================================================================
    # 2. NO ACTION RECOMMENDATIONS
    # Examples:
    # - Continue monitoring
    # - No immediate sales intervention
    # - Monitor inventory movement
    # =========================================================================
    elif cls == "No Action":
        priority = "Low"
        if aged_qty == 0:
            drivers.append("Zero aged stock")
            if mtc < 1.5:
                drivers.append("Rapid organic turnover")
                action = "No immediate sales intervention; continue monitoring"
                reason = (
                    f"Zero aged stock in warehouse with rapid clearance runway ({mtc:.1f} months); "
                    "maintain standard replenishment schedule with no immediate sales intervention."
                )
            else:
                drivers.append("Standard movement monitoring")
                action = "Continue monitoring & monitor inventory movement"
                reason = (
                    f"Zero aged stock currently in 91+ day buckets, with a clearance runway of {mtc:.1f} months; "
                    "continue monitoring and track inventory movement as stock reaches 60 days."
                )
        else:
            drivers.append(f"Minor aged stock ({aged_qty:,.0f} units)")
            drivers.append("Clearance runway below 3 months")
            action = "Continue monitoring inventory movement"
            reason = (
                f"Holds {aged_qty:,.0f} aged units (₹{aged_val:,.0f}), but monthly sales velocity "
                f"({avg_sales:.1f} units/month) organically clears stock in {mtc:.2f} months without discounting."
            )

    # =========================================================================
    # 3. PUSH RECOMMENDATIONS
    # Examples:
    # - Create sales outreach list
    # - Prioritize high-value customers
    # - Push through targeted sales activity
    # - Monitor clearance progress
    # Differentiated based on:
    # - High aged value
    # - High months to clear
    # - High inventory value
    # - Declining sales
    # - Low sales velocity
    # =========================================================================
    elif cls == "Push":
        if is_high_aged_val:
            drivers.append(f"High aged value (₹{aged_val:,.0f})")
        if is_high_mtc:
            drivers.append(f"High months to clear ({mtc:.1f}m)" if not np.isinf(mtc) else "Stagnant clearance runway (∞)")
        if is_high_inv_val:
            drivers.append(f"High inventory value (₹{inv_val:,.0f})")
        if is_dec:
            drivers.append(f"Declining sales trend ({trend_pct:+.1f}%)" if trend_pct != 0 else "Declining sales trend")
        if is_low_velocity:
            drivers.append(f"Low sales velocity ({avg_sales:.1f} units/mth)")

        # Differentiated decision logic:
        # Case A: Compound high exposure (High Aged Value AND (High MTC or Declining Sales or High Inv Value))
        if is_high_aged_val and (is_high_mtc or is_dec or is_high_inv_val):
            priority = "Urgent"
            action = "Prioritize high-value customers & push through targeted sales activity"
            sub_reasons = []
            if is_high_aged_val:
                sub_reasons.append(f"high aged value (₹{aged_val:,.0f})")
            if is_high_mtc:
                sub_reasons.append(f"high months to clear ({mtc:.1f} months)")
            if is_high_inv_val:
                sub_reasons.append(f"high total inventory value (₹{inv_val:,.0f})")
            if is_dec:
                sub_reasons.append(f"declining sales trend ({trend_pct:+.1f}%)" if trend_pct != 0 else "declining sales trend")
            reason = (
                f"Severe slow-stock exposure with {', '.join(sub_reasons)}; "
                "urgently prioritize high-value customers across Buckets 1 & 2 and push through targeted sales activity."
            )

        # Case B: High Aged Value standalone focus
        elif is_high_aged_val:
            priority = "High"
            action = "Create sales outreach list & prioritize high-value customers"
            reason = (
                f"High aged inventory value (₹{aged_val:,.0f}) tied up in warehouse stock; "
                "create targeted sales outreach list prioritizing top purchasing accounts in Bucket 1 and Bucket 2."
            )

        # Case C: High Months to Clear / Low Sales Velocity focus
        elif is_high_mtc or is_low_velocity:
            priority = "High"
            action = "Push through targeted sales activity & prioritize high-value customers"
            mtc_text = f"high clearance runway of {mtc:.1f} months" if not np.isinf(mtc) else "stagnant clearance runway"
            vel_text = f"low sales velocity of {avg_sales:.1f} units/month"
            reason = (
                f"Driven by {mtc_text} and {vel_text}; push through targeted sales activity across "
                "Bucket 2 (industry peers) and Bucket 3 (category buyers) to accelerate clearance."
            )

        # Case D: High Inventory Value standalone focus
        elif is_high_inv_val:
            priority = "High"
            action = "Create sales outreach list & prioritize high-value customers"
            reason = (
                f"High total inventory value (₹{inv_val:,.0f}) with {aged_qty:,.0f} units of aged stock; "
                "create sales outreach list and prioritize high-value wholesale accounts to protect working capital."
            )

        # Case E: Declining Sales standalone focus
        elif is_dec:
            priority = "High"
            action = "Create sales outreach list & push through targeted sales activity"
            trend_str = f"({trend_pct:+.1f}%)" if trend_pct != 0 else ""
            reason = (
                f"Declining sales momentum {trend_str} with {aged_qty:,.0f} aged units (₹{aged_val:,.0f}); "
                "create sales outreach list to re-engage historical Bucket 1 accounts before demand further drops."
            )

        # Case F: Moderate Push (Manageable runway, moderate value)
        else:
            priority = "Medium"
            action = "Push through targeted sales activity & monitor clearance progress"
            reason = (
                f"Moderate aged stock (₹{aged_val:,.0f}, {aged_qty:,.0f} units) with {mtc:.1f} months to clear; "
                "push through targeted sales activity and monitor clearance progress on a weekly schedule."
            )

    # =========================================================================
    # 4. INACTIVE CATALOG ITEMS (Rule R4)
    # =========================================================================
    else:
        status = str(d.get("Status", "Active")).strip().title()
        if status == "Inactive":
            if total_stock > 0:
                drivers.append("Inactive status with stock (Rule R4)")
                priority = "High"
                action = "Review obsolete inventory & consider liquidation/discontinuation"
                reason = (
                    f"Inactive catalog item holding {total_stock:,.0f} units (₹{inv_val:,.0f}) in warehouse stock; "
                    "stop unnecessary replenishment and evaluate scrap, liquidation, or vendor return per Rule R4."
                )
            else:
                drivers.append("Inactive status, zero stock (Rule R4)")
                priority = "Low"
                action = "Stop unnecessary replenishment"
                reason = "Inactive catalog SKU with zero stock; ensure system purchasing locks prevent accidental reorders."
        else:
            priority = "Medium"
            action = "Review item viability"
            reason = f"Perform standard catalog review for {sku}."

    return {
        "sku": sku,
        "classification": cls,
        "action": action,
        "recommended_action": action,
        "priority": priority,
        "reason": reason,
        "action_reason": reason,
        "drivers": drivers,
    }


def evaluate_recommended_actions(items, sales_lines=None, switch_map=None):
    """
    Applies the deterministic Recommended Action Engine across an entire items DataFrame.

    Enriches the DataFrame with:
      - 'Recommended Action': Specific operational action
      - 'Priority': Priority tier ('Urgent', 'High', 'Medium', 'Low')
      - 'Reason': Deterministic, explainable rationale
      - 'Action Reason': Alias for 'Reason'

    Does NOT modify R1-R7 classifications. Never uses AI.
    """
    df = items.copy()
    if df.empty:
        df["Recommended Action"] = []
        df["Priority"] = []
        df["Reason"] = []
        df["Action Reason"] = []
        return df

    trends = compute_sales_trends(sales_lines, switch_map=switch_map)

    actions = []
    priorities = []
    reasons = []

    for _, row in df.iterrows():
        sku = str(row.get("SKU", "")).strip().upper()
        trend_info = trends.get(sku, {})
        is_dec = trend_info.get("declining", False)
        trend_pct = trend_info.get("trend_pct", 0.0)

        rec = recommend_operational_action(row, is_declining=is_dec, sales_trend_pct=trend_pct)
        actions.append(rec["action"])
        priorities.append(rec["priority"])
        reasons.append(rec["reason"])

    df["Recommended Action"] = actions
    df["Priority"] = priorities
    df["Reason"] = reasons
    df["Action Reason"] = reasons
    return df


def generate_sku_classification_explanation(item_data, config=None):
    """
    Generates a deterministic classification explanation for any catalog SKU based on Rule R5.

    Explains the exact business logic decision:
      - For Push: Explains 6M Sales Qty, Master Pack, Aged Qty, Aged Value, Avg Monthly Sales,
        Months to Clear, Inventory Value, Risk Score, and Risk Level.
      - For No Action: Explicitly distinguishes whether the reason is:
        * 'No aged stock' OR
        * 'Months to Clear below 3' (or custom threshold)
      - For Red List: Explicitly explains that 6M Sales Qty < 1 Master Pack (or custom multiplier).

    Returns a dictionary with:
      - 'sku': SKU identifier
      - 'classification': Red List, No Action, or Push
      - 'explanation': Fully deterministic sentence template using calculated metrics
      - 'rule_triggered': The formal Rule R5 sub-clause triggered
      - 'reason_summary': Concise trigger summary
      - 'recommended_action': Operational guidance for commercial / category teams
      - 'supporting_metrics': Dictionary containing all 9 required metrics
    """
    if config is None:
        config = get_default_config()

    if hasattr(item_data, "to_dict"):
        d = item_data.to_dict()
    elif isinstance(item_data, dict):
        d = item_data
    else:
        d = dict(item_data)

    raw_sku = d.get("SKU")
    if not raw_sku and hasattr(item_data, "name") and item_data.name:
        raw_sku = item_data.name
    sku = str(raw_sku).strip() if raw_sku else "Unknown SKU"
    d["SKU"] = sku
    cls = str(d.get("Class", "")).strip()

    def _to_float(v, default=0.0):
        try:
            val = float(v)
            return default if (pd.isna(val) or np.isnan(val)) else val
        except (ValueError, TypeError):
            return default

    sales_qty = _to_float(d.get("6M Sales Qty", 0))
    master_pack = _to_float(d.get("Master Pack Qty", 0))
    aged_qty = _to_float(d.get("Aged Qty", 0))
    aged_val = _to_float(d.get("Aged Value", 0))
    unit_cost = _to_float(d.get("Unit Cost (Rs)", 0))
    total_stock = _to_float(d.get("Total Stock", 0))

    if "Avg Monthly Sales" in d:
        avg_sales = _to_float(d.get("Avg Monthly Sales", 0))
    else:
        avg_sales = sales_qty / 6.0

    if "Months to Clear" in d:
        mtc_raw = d.get("Months to Clear")
        if mtc_raw == float("inf") or (isinstance(mtc_raw, str) and "inf" in mtc_raw.lower()):
            mtc = np.inf
        else:
            mtc = _to_float(mtc_raw, np.inf)
    else:
        mtc = np.inf if avg_sales <= 0 else total_stock / avg_sales

    if "Inventory Value" in d:
        inv_val = _to_float(d.get("Inventory Value", 0))
    else:
        inv_val = total_stock * unit_cost

    risk_score = int(_to_float(d.get("Risk Score", 0)))
    risk_level = str(d.get("Risk Level", "Medium")).strip()

    if np.isinf(mtc):
        mtc_str = "∞ (cannot clear at current sales rate)" if sales_qty == 0 else "∞"
    else:
        mtc_str = f"{mtc:.1f}"

    mtc_thresh = config.months_to_clear_threshold
    mtc_str_thresh = f"{mtc_thresh:.1f}".rstrip("0").rstrip(".") if mtc_thresh != int(mtc_thresh) else f"{int(mtc_thresh)}"
    mp_mult = config.red_list_mp_multiplier
    mp_mult_str = f"{mp_mult:.1f}".rstrip("0").rstrip(".") if mp_mult != int(mp_mult) else f"{int(mp_mult)}"
    aging_days = config.aging_days_threshold

    # Strict R5 Classification Explanation
    if cls == "Push":
        if config.is_default():
            explanation = (
                f"{sku} is classified as PUSH because it has aged inventory and its months to clear "
                f"exceeds the 3-month threshold. The item has ₹{aged_val:,.0f} of aged inventory value "
                f"and an estimated {mtc_str} months to clear."
            )
            rule_triggered = "Rule R5 — Step 3: Push Criteria (Aged Qty > 0 and Months to Clear >= 3)"
            reason_summary = "Aged inventory & Months to Clear >= 3"
        else:
            explanation = (
                f"{sku} is classified as PUSH because it has aged inventory and its months to clear "
                f"exceeds the {mtc_str_thresh}-month threshold. The item has ₹{aged_val:,.0f} of aged inventory value "
                f"and an estimated {mtc_str} months to clear."
            )
            rule_triggered = f"Custom Rule R5 — Step 3: Push Criteria (Aged Qty > 0 and Months to Clear >= {mtc_str_thresh})"
            reason_summary = f"Aged inventory & Months to Clear >= {mtc_str_thresh}"

        recommended_action = (
            f"Initiate proactive customer liquidation across Bucket 1 (prior buyers), "
            f"Bucket 2 (similar industry accounts), and Bucket 3 (same-category buyers) "
            f"to liquidate {aged_qty:,.0f} aged units and recover ₹{aged_val:,.0f} in capital."
        )

    elif cls == "No Action":
        if aged_qty == 0 and mtc < mtc_thresh:
            if config.is_default():
                reason_summary = "No aged stock (and Months to Clear below 3)"
                explanation = (
                    f"{sku} is classified as NO ACTION because it has zero aged stock "
                    f"(0 units in 91+ day aging buckets) and its months to clear is below 3 "
                    f"({mtc:.2f} months). Warehouse inventory is fully fresh and actively turning over."
                )
                rule_triggered = "Rule R5 — Step 2: No Action Criteria (Zero Aged Stock & Months to Clear < 3)"
            else:
                reason_summary = f"No aged stock (and Months to Clear below {mtc_str_thresh})"
                explanation = (
                    f"{sku} is classified as NO ACTION because it has zero aged stock "
                    f"(0 units in {aging_days}+ day aging buckets) and its months to clear is below {mtc_str_thresh} "
                    f"({mtc:.2f} months). Warehouse inventory is fully fresh and actively turning over."
                )
                rule_triggered = f"Custom Rule R5 — Step 2: No Action Criteria (Zero Aged Stock & Months to Clear < {mtc_str_thresh})"
            recommended_action = (
                "Maintain standard replenishment and inventory monitoring; no liquidation or push campaigns required."
            )
        elif aged_qty == 0:
            reason_summary = "No aged stock"
            if config.is_default():
                explanation = (
                    f"{sku} is classified as NO ACTION because it has no aged stock "
                    f"(0 units in 91+ day aging buckets). All current warehouse inventory is fresh "
                    f"(within 0-90 days), so no liquidation intervention is required."
                )
                rule_triggered = "Rule R5 — Step 2: No Action Criteria (No aged stock)"
            else:
                explanation = (
                    f"{sku} is classified as NO ACTION because it has no aged stock "
                    f"(0 units in {aging_days}+ day aging buckets). All current warehouse inventory is fresh, "
                    f"so no liquidation intervention is required."
                )
                rule_triggered = "Custom Rule R5 — Step 2: No Action Criteria (No aged stock)"
            recommended_action = (
                "Maintain standard stocking levels and monitor movement pace as stock enters the 60-90 day window."
            )
        else:  # mtc < mtc_thresh
            if config.is_default():
                reason_summary = "Months to Clear below 3"
                explanation = (
                    f"{sku} is classified as NO ACTION because its months to clear is below 3 "
                    f"({mtc:.2f} months). Although it holds {aged_qty:,.0f} units of aged stock "
                    f"(₹{aged_val:,.0f}), its monthly sales velocity ({avg_sales:.1f} units/month) "
                    f"is strong enough to clear current stock organically without discounting."
                )
                rule_triggered = "Rule R5 — Step 2: No Action Criteria (Months to Clear below 3)"
            else:
                reason_summary = f"Months to Clear below {mtc_str_thresh}"
                explanation = (
                    f"{sku} is classified as NO ACTION because its months to clear is below {mtc_str_thresh} "
                    f"({mtc:.2f} months). Although it holds {aged_qty:,.0f} units of aged stock "
                    f"(₹{aged_val:,.0f}), its monthly sales velocity ({avg_sales:.1f} units/month) "
                    f"is strong enough to clear current stock organically without discounting."
                )
                rule_triggered = f"Custom Rule R5 — Step 2: No Action Criteria (Months to Clear below {mtc_str_thresh})"
            recommended_action = (
                "Allow normal customer demand to clear remaining aged inventory; review again in 30 days."
            )

    elif cls == "Red List":
        target_mp = master_pack * mp_mult
        if config.is_default():
            reason_summary = "6M Sales Qty < 1 Master Pack"
            extra_note = (
                " No sales were recorded during the 6-month period, so the item cannot be expected to clear at the current sales rate."
                if sales_qty == 0
                else f" Sales volume of {sales_qty:,.0f} units is insufficient to justify stocking full commercial packs."
            )
            explanation = (
                f"{sku} is classified as RED LIST because 6M Sales Qty < 1 Master Pack: "
                f"6-month sales ({sales_qty:,.0f} units) failed to reach the commercial minimum of 1 Master Pack "
                f"({master_pack:,.0f} units).{extra_note}"
            )
            rule_triggered = "Rule R5 — Step 1: Red List Criteria (6M Sales Qty < 1 Master Pack)"
        else:
            reason_summary = f"6M Sales Qty < {mp_mult_str} Master Pack"
            extra_note = (
                " No sales were recorded during the 6-month period, so the item cannot be expected to clear at the current sales rate."
                if sales_qty == 0
                else f" Sales volume of {sales_qty:,.0f} units is insufficient to reach the threshold ({target_mp:,.0f} units)."
            )
            explanation = (
                f"{sku} is classified as RED LIST because 6M Sales Qty < {mp_mult_str} Master Pack: "
                f"6-month sales ({sales_qty:,.0f} units) failed to reach the threshold of {mp_mult_str} Master Pack "
                f"({target_mp:,.0f} units).{extra_note}"
            )
            rule_triggered = f"Custom Rule R5 — Step 1: Red List Criteria (6M Sales Qty < {mp_mult_str} Master Pack)"

        recommended_action = (
            "Initiate commercial review with Category Management / Sourcing for supplier MOQ renegotiation, "
            "pack-size rationalization, vendor buyback, or phased product retirement."
        )

    else:
        # Fallback for unclassified / inactive items
        status = str(d.get("Status", "Active")).strip().title()
        if status == "Inactive":
            reason_summary = "Inactive catalog status (Rule R4)"
            explanation = (
                f"{sku} is an Inactive catalog item and is excluded from the active slow stock "
                f"pipeline per Rule R4."
            )
            rule_triggered = "Rule R4: Inactive Item Stock Isolation"
            recommended_action = (
                "Manage under Inactive Stock Report for supplier return, write-off, or scrap salvage."
            )
        else:
            reason_summary = "Standard review"
            explanation = f"{sku} status review under evaluation."
            rule_triggered = "General Inventory Policy"
            recommended_action = "Review SKU performance parameters."

    supporting_metrics = {
        "6M Sales Qty": sales_qty,
        "Master Pack": master_pack,
        "Aged Qty": aged_qty,
        "Aged Value": aged_val,
        "Avg Monthly Sales": avg_sales,
        "Months to Clear": mtc,
        "Inventory Value": inv_val,
        "Risk Score": risk_score,
        "Risk Level": risk_level,
    }

    action_info = recommend_operational_action(d)
    action = d.get("Recommended Action", action_info["action"])
    priority = d.get("Priority", action_info["priority"])
    action_reason = d.get("Reason", d.get("Action Reason", action_info["reason"]))

    return {
        "sku": sku,
        "classification": cls,
        "explanation": explanation,
        "rule_triggered": rule_triggered,
        "reason_summary": reason_summary,
        "recommended_action": action,
        "action": action,
        "priority": priority,
        "reason": action_reason,
        "action_reason": action_reason,
        "drivers": action_info.get("drivers", []),
        "supporting_metrics": supporting_metrics,
    }


def run_analysis(item_master, stock_aging, sales_lines, customers, validation=None, config=None):
    """
    Executes the slow stock analysis applying rules R3, R4, R5:
      R3: Consolidates SWITCH old items into new items under the new SKU.
      R4: Excludes inactive items from main analysis; separately reports
          inactive items holding stock.
      R5: Computes Total Stock, Aged Qty, Aged Value, Avg Monthly Sales,
          and Months to Clear, then applies classification in strict order:
          1. Red List if 6-month sales quantity < 1 Master Pack (or config.red_list_mp_multiplier * MP)
          2. Otherwise No Action if Aged Quantity = 0 OR Months to Clear < config.months_to_clear_threshold
          3. Otherwise Push
    """
    if config is None:
        config = get_default_config()

    im = item_master.copy()
    stock = stock_aging.copy()
    sales = sales_lines.copy()
    cust = customers.copy()

    # Standardisation
    for df in [im, stock, sales]:
        df["SKU"] = _normalise_text(df["SKU"])
    sales["CustomerID"] = _normalise_text(sales["CustomerID"])
    cust["CustomerID"] = _normalise_text(cust["CustomerID"])

    im["Status"] = im["Status"].astype(str).str.strip().str.title()
    im["Alternate Flag"] = im["Alternate Flag"].astype(str).str.strip().str.upper()
    im["Item Name"] = im["Item Name"].astype(str).str.strip()
    im["Category"] = im["Category"].astype(str).str.strip()

    cust["Industry"] = cust["Industry"].replace(["nan", "None", ""], np.nan)
    cust["Industry"] = cust["Industry"].apply(lambda x: x.strip() if isinstance(x, str) else x)

    # Remove exact duplicate sales lines
    sales = sales.drop_duplicates().copy()

    # Numeric conversion
    stock_cols = [
        "Qty 0-30 days", "Qty 31-60 days", "Qty 61-90 days",
        "Qty 91-180 days", "Qty 180+ days"
    ]
    for c in stock_cols:
        stock[c] = pd.to_numeric(stock[c], errors="coerce").fillna(0)

    sales["Qty"] = pd.to_numeric(sales["Qty"], errors="coerce").fillna(0)
    sales["Value (Rs)"] = pd.to_numeric(sales["Value (Rs)"], errors="coerce").fillna(0)
    im["Master Pack Qty"] = pd.to_numeric(im["Master Pack Qty"], errors="coerce")
    im["Unit Cost (Rs)"] = pd.to_numeric(im["Unit Cost (Rs)"], errors="coerce")

    # R3: Pack-size switches
    switch_map, switch_map_df = build_switch_map(im)
    sales["Analysis_SKU"] = sales["SKU"].replace(switch_map)
    stock["Analysis_SKU"] = stock["SKU"].replace(switch_map)

    # R4: Inactive stock report before filtering
    # Compute total stock directly from stock aging table for each SKU
    raw_stock_totals = stock.groupby("SKU")[stock_cols].sum().sum(axis=1)
    im["Total Stock"] = im["SKU"].map(raw_stock_totals).fillna(0)

    inactive_items = im[im["Status"] == "Inactive"].copy()
    inactive_stock = inactive_items[inactive_items["Total Stock"] > 0][[
        "SKU", "Item Name", "Category", "Total Stock", "Unit Cost (Rs)"
    ]].copy()
    inactive_stock["Total Stock Value"] = (
        inactive_stock["Total Stock"] * inactive_stock["Unit Cost (Rs)"]
    )

    # Active item master only. Old SKUs participating in a SWITCH are excluded
    # from the main analytical items because all stock and sales are reported under the new SKU.
    old_switch_skus = set(switch_map.keys())
    active_im = im[(im["Status"] == "Active") & (~im["SKU"].isin(old_switch_skus))].copy()

    # Stock aggregation at final analysis SKU
    stock_agg = (
        stock.groupby("Analysis_SKU")[stock_cols]
        .sum()
        .reset_index()
        .rename(columns={"Analysis_SKU": "SKU"})
    )

    # Sales aggregation at final analysis SKU
    sales_agg = (
        sales.groupby("Analysis_SKU")
        .agg(
            **{
                "6M Sales Qty": ("Qty", "sum"),
                "6M Sales Value": ("Value (Rs)", "sum"),
            }
        )
        .reset_index()
        .rename(columns={"Analysis_SKU": "SKU"})
    )

    # Merge active items with aggregated stock and sales
    items = active_im.merge(
        stock_agg,
        on="SKU",
        how="left",
        suffixes=("", "_stock")
    ).merge(
        sales_agg,
        on="SKU",
        how="left"
    )

    for c in stock_cols + ["6M Sales Qty", "6M Sales Value"]:
        if c in items.columns:
            items[c] = pd.to_numeric(items[c], errors="coerce").fillna(0)

    # R5: Stock Metrics calculation
    # Total Stock = Qty 0-30 + Qty 31-60 + Qty 61-90 + Qty 91-180 + Qty 180+
    items["Total Stock"] = items[stock_cols].sum(axis=1)

    # Working Capital: Total Inventory Value = Total Stock * Unit Cost
    items["Inventory Value"] = items["Total Stock"] * items["Unit Cost (Rs)"]

    # Aged Quantity based on config.aging_days_threshold (Default 91+ days)
    if config.aging_days_threshold <= 31:
        items["Aged Qty"] = items["Qty 31-60 days"] + items["Qty 61-90 days"] + items["Qty 91-180 days"] + items["Qty 180+ days"]
    elif config.aging_days_threshold <= 61:
        items["Aged Qty"] = items["Qty 61-90 days"] + items["Qty 91-180 days"] + items["Qty 180+ days"]
    else:
        items["Aged Qty"] = items["Qty 91-180 days"] + items["Qty 180+ days"]

    # Aged Value = Aged Quantity * Unit Cost
    items["Aged Value"] = items["Aged Qty"] * items["Unit Cost (Rs)"]

    # Average Monthly Sales = 6-month Sales Quantity / 6
    items["Avg Monthly Sales"] = items["6M Sales Qty"] / 6.0

    # Months to Clear = Total Stock / Average Monthly Sales
    # If Average Monthly Sales <= 0, avoid division by zero and assign np.inf
    def _calc_months_to_clear(row):
        avg_s = float(row.get("Avg Monthly Sales", 0.0) or 0.0)
        tot_s = float(row.get("Total Stock", 0.0) or 0.0)
        if avg_s > 0.0:
            return tot_s / avg_s
        return np.inf

    items["Months to Clear"] = items.apply(_calc_months_to_clear, axis=1)

    # R5: CLASSIFICATION ORDER (Strict Order: 1. Red List -> 2. No Action -> 3. Push)
    def classify(row):
        # 1. Red List if 6-month sales quantity < multiplier * Master Pack
        if row["6M Sales Qty"] < (row["Master Pack Qty"] * config.red_list_mp_multiplier):
            return "Red List"
        # 2. Otherwise No Action if Aged Quantity = 0 OR Months to Clear < threshold
        if row["Aged Qty"] == 0 or row["Months to Clear"] < config.months_to_clear_threshold:
            return "No Action"
        # 3. Otherwise Push
        return "Push"

    items["Class"] = items.apply(classify, axis=1)

    # Deterministic Inventory Risk Score (0-100) and drivers (does NOT override R5 Class)
    items = calculate_inventory_risk(items, config=config)

    # Deterministic Recommended Action Engine (Rule R1-R7 compliant)
    items = evaluate_recommended_actions(items, sales_lines=sales, switch_map=switch_map)

    # Deterministic SKU Classification Explanations (Rule R5 explainability)
    explanations = items.apply(lambda r: generate_sku_classification_explanation(r, config=config), axis=1)
    items["Classification Explanation"] = [e["explanation"] for e in explanations]
    items["Rule Triggered"] = [e["rule_triggered"] for e in explanations]
    items["Classification Reason"] = [e["reason_summary"] for e in explanations]
    items["Recommended Action"] = [e["recommended_action"] for e in explanations]
    items["Priority"] = [e["priority"] for e in explanations]
    items["Reason"] = [e["reason"] for e in explanations]
    items["Action Reason"] = [e["action_reason"] for e in explanations]

    # Sales Trend Analysis (Decision-Support Metric only - does NOT alter R1-R7 classification)
    sales_trends = calculate_monthly_sales_trends(sales_lines=sales, items=items, switch_map=switch_map)
    summary_df = sales_trends.get("summary_df", pd.DataFrame())
    if not summary_df.empty and "SKU" in summary_df.columns:
        trend_cols = [
            "SKU", "Sales Trend", "Sales Trend Reason",
            "Latest Month", "Latest Month Qty", "Previous Month", "Previous Month Qty",
            "Sales Growth Qty", "Sales Growth %"
        ]
        avail_t_cols = [c for c in trend_cols if c in summary_df.columns]
        items = items.merge(summary_df[avail_t_cols], on="SKU", how="left")
        items["Latest Month Sales"] = items.get("Latest Month Qty", None)
        items["Previous Month Sales"] = items.get("Previous Month Qty", None)
    else:
        for c in ["Sales Trend", "Sales Trend Reason", "Latest Month", "Latest Month Qty", "Previous Month", "Previous Month Qty", "Sales Growth Qty", "Sales Growth %", "Latest Month Sales", "Previous Month Sales"]:
            if c not in items.columns:
                items[c] = None
        items["Sales Trend"] = "No Sales"

    # Sales Priority Score for Push Items (Commercial liquidation urgency & opportunity)
    items = calculate_sales_priority(items, sales_trends=sales_trends, config=config)
    ranked_push_table = get_ranked_push_table(items, sales_trends=sales_trends, config=config)

    # Sort items for presentation: Class ascending, Aged Value descending
    items = items.sort_values(
        ["Class", "Aged Value"],
        ascending=[True, False]
    ).reset_index(drop=True)

    # Calculate Working Capital Impact & Cash at Risk
    working_capital = calculate_working_capital_impact(items)

    # Dead Stock Analysis (Items where 6M Sales Qty = 0; analytical view only, does not change R1-R7)
    dead_stock_df = identify_dead_stock(items, sales_df=sales)
    dead_stock_summary = get_dead_stock_summary(
        dead_stock_df,
        total_inventory_value=working_capital["summary"]["total_inventory_value"],
        total_aged_value=working_capital["summary"]["aged_inventory_value"]
    )
    cls_counts = items["Class"].value_counts().to_dict()
    logger.info(
        "run_analysis complete: %d active SKUs (Push: %d, Red List: %d, No Action: %d, Inactive with Stock: %d)",
        len(items), cls_counts.get("Push", 0), cls_counts.get("Red List", 0), cls_counts.get("No Action", 0), len(inactive_stock)
    )

    return {
        "analysis_items": items,
        "clean_item_master": active_im,
        "full_item_master": im,
        "clean_stock": stock,
        "clean_sales": sales,
        "clean_customers": cust,
        "inactive_stock": inactive_stock,
        "switch_map": switch_map,
        "switch_map_df": switch_map_df,
        "working_capital": working_capital,
        "sales_trends": sales_trends,
        "ranked_push_table": ranked_push_table,
        "dead_stock": dead_stock_df,
        "dead_stock_summary": dead_stock_summary,
        "config": config,
    }


def build_audit_trail(raw, validation, analysis, targets, config=None):
    """
    Constructs an end-to-end transformation audit trail covering:
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
    if config is None:
        config = analysis.get("config", get_default_config())

    im_raw, stock_raw, sales_raw, cust_raw = raw
    items = analysis["analysis_items"]

    n_uploaded_im = len(im_raw)
    n_uploaded_stock = len(stock_raw)
    n_uploaded_sales = len(sales_raw)
    n_uploaded_cust = len(cust_raw)
    total_uploaded = n_uploaded_im + n_uploaded_stock + n_uploaded_sales + n_uploaded_cust

    dups_detected = validation.get("duplicate_sales_rows", 0)
    dups_removed = dups_detected

    sku_corrections = 0
    cust_id_corrections = 0
    for iss in validation.get("issues", []):
        prob = iss.get("Problem", "").lower()
        if "sku formatting" in prob:
            sku_corrections += int(iss.get("Count", 0))
        elif "customerid formatting" in prob:
            cust_id_corrections += int(iss.get("Count", 0))

    switch_count = len(analysis.get("switch_map", {}))
    inactive_excluded = int((im_raw["Status"].astype(str).str.strip().str.upper() == "INACTIVE").sum())
    inactive_holding_stock = len(analysis.get("inactive_stock", pd.DataFrame()))

    clean_sales = analysis.get("clean_sales", pd.DataFrame())
    elig_threshold = config.customer_eligibility_spend
    if not clean_sales.empty:
        cust_spend = clean_sales.groupby("CustomerID")["Value (Rs)"].sum()
        eligible_customers = int((cust_spend > elig_threshold).sum())
    else:
        eligible_customers = 0

    push_items_count = int((items["Class"] == "Push").sum())
    targets_generated_count = sum(len(df) for df in targets.values())

    trail_records = [
        {
            "Step": 1,
            "Stage": "1. Ingestion",
            "Audit Metric": "Number of uploaded records",
            "Count": total_uploaded,
            "Formatted Value": f"{total_uploaded:,} records",
            "Operational Detail": f"Item_Master ({n_uploaded_im}), Stock_Aging ({n_uploaded_stock}), Sales_Lines ({n_uploaded_sales}), Customers ({n_uploaded_cust})",
        },
        {
            "Step": 2,
            "Stage": "2. Data Cleansing",
            "Audit Metric": "Number of exact duplicates detected",
            "Count": dups_detected,
            "Formatted Value": f"{dups_detected:,} rows",
            "Operational Detail": "Exact duplicate transaction rows identified in Sales_Lines",
        },
        {
            "Step": 3,
            "Stage": "2. Data Cleansing",
            "Audit Metric": "Number of duplicates removed",
            "Count": dups_removed,
            "Formatted Value": f"{dups_removed:,} rows",
            "Operational Detail": "Redundant sales rows purged before run-rate calculation to avoid inflating velocity",
        },
        {
            "Step": 4,
            "Stage": "2. Data Cleansing",
            "Audit Metric": "Number of SKU formatting corrections",
            "Count": sku_corrections,
            "Formatted Value": f"{sku_corrections:,} corrections",
            "Operational Detail": "Whitespace trimmed and casing converted to uppercase in Sales_Lines",
        },
        {
            "Step": 5,
            "Stage": "2. Data Cleansing",
            "Audit Metric": "Number of customer ID formatting corrections",
            "Count": cust_id_corrections,
            "Formatted Value": f"{cust_id_corrections:,} corrections",
            "Operational Detail": "Customer IDs standardized to uppercase trimmed format",
        },
        {
            "Step": 6,
            "Stage": "3. Catalog Consolidation",
            "Audit Metric": "Number of SWITCH mappings",
            "Count": switch_count,
            "Formatted Value": f"{switch_count:,} mappings",
            "Operational Detail": "Rule R3: Pack-size consolidations merging historical sales & stock under new SKUs",
        },
        {
            "Step": 7,
            "Stage": "3. Catalog Consolidation",
            "Audit Metric": "Number of inactive items excluded",
            "Count": inactive_excluded,
            "Formatted Value": f"{inactive_excluded:,} items",
            "Operational Detail": "Rule R4: Inactive catalog items excluded from active sales classification",
        },
        {
            "Step": 8,
            "Stage": "3. Catalog Consolidation",
            "Audit Metric": "Number of inactive items still holding stock",
            "Count": inactive_holding_stock,
            "Formatted Value": f"{inactive_holding_stock:,} items",
            "Operational Detail": "Rule R4: Inactive items with physical warehouse inventory isolated for audit",
        },
        {
            "Step": 9,
            "Stage": "4. Customer Targeting",
            "Audit Metric": "Number of eligible customers",
            "Count": eligible_customers,
            "Formatted Value": f"{eligible_customers:,} accounts",
            "Operational Detail": f"Rule R6: Accounts qualifying with 6-month purchase turnover > ₹{elig_threshold:,.0f}",
        },
        {
            "Step": 10,
            "Stage": "4. Customer Targeting",
            "Audit Metric": "Number of Push items",
            "Count": push_items_count,
            "Formatted Value": f"{push_items_count:,} items",
            "Operational Detail": f"Rule R5: Catalog items requiring proactive push (Aged Qty > 0 and Months to Clear >= {config.months_to_clear_threshold:.1f}".rstrip('0').rstrip('.') + ")",
        },
        {
            "Step": 11,
            "Stage": "4. Customer Targeting",
            "Audit Metric": "Number of customer targets generated",
            "Count": targets_generated_count,
            "Formatted Value": f"{targets_generated_count:,} recommendations",
            "Operational Detail": "Rules R6–R7: Waterfalled targets across Bucket 1, Bucket 2, and Bucket 3",
        },
    ]

    return {
        "metrics": {
            "uploaded_records": total_uploaded,
            "duplicates_detected": dups_detected,
            "duplicates_removed": dups_removed,
            "sku_formatting_corrections": sku_corrections,
            "customer_id_formatting_corrections": cust_id_corrections,
            "switch_mappings": switch_count,
            "inactive_items_excluded": inactive_excluded,
            "inactive_items_still_holding_stock": inactive_holding_stock,
            "eligible_customers": eligible_customers,
            "push_items": push_items_count,
            "customer_targets_generated": targets_generated_count,
        },
        "table": pd.DataFrame(trail_records),
    }
