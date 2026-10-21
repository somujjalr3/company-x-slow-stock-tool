"""
Dead Stock Analysis Module for Company X Slow Stock Action Tool.

Specialized analytical diagnostic identifying completely stagnant catalog items:
Criteria:
  6M Sales Qty = 0

Key Capabilities:
1. identify_dead_stock():
   Identifies and isolates catalog items holding zero sales movement in the 6-month review window.
   Extracts last available sales information and maps all 10 required columns:
     - SKU
     - Description (Item Name)
     - Category
     - Total Stock
     - Inventory Value
     - Aged Qty
     - Aged Value
     - Last Available Sales Information
     - Risk Score
     - Recommended Action

2. get_dead_stock_summary():
   Computes Dead Stock KPIs (SKU count, Total Inventory Value, Aged Value / Cash at Risk,
   total units, and percentage of company inventory capital).

3. get_top_dead_stock_by_value():
   Ranks Dead Stock items strictly by Inventory Value descending to highlight highest capital exposure.

CRITICAL INVARIANTS:
- Does NOT alter Rules R1-R7.
- Dead Stock is strictly an analytical diagnostic view, NOT a replacement for Red List classification.
- Inactive items remain segregated under Rule R4.
- 100% deterministic, explainable calculations without AI.
"""

import io
import math
from typing import Dict, List, Tuple, Any, Optional
import numpy as np
import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from src.logger import get_logger
from src.sales_trends import parse_and_sort_months

logger = get_logger("DeadStock")


def generate_dead_stock_action(row: dict) -> str:
    """
    Deterministic operational recommended action for completely stagnant (dead) stock.
    """
    total_stock = float(row.get("Total Stock", 0.0))
    inv_val = float(row.get("Inventory Value", 0.0))
    aged_val = float(row.get("Aged Value", 0.0))
    unit_cost = float(row.get("Unit Cost (Rs)", 0.0))

    if inv_val >= 40000.0 or aged_val >= 15000.0:
        return (
            "Freeze replenishment immediately; initiate formal liquidation / vendor return review "
            "to release trapped working capital; evaluate scrap write-off for unsaleable units."
        )
    elif aged_val > 0.0:
        return (
            "Halt replenishment; review obsolete inventory with category manager; "
            "bundle with fast-moving items or discount heavily for bulk disposal."
        )
    else:
        return (
            "Halt replenishment orders; investigate zero sales demand; "
            "verify whether item is recently listed, misplaced, or commercially obsolete."
        )


def identify_dead_stock(
    items_df: pd.DataFrame,
    sales_df: pd.DataFrame = None,
) -> pd.DataFrame:
    """
    Identifies catalog items where 6M Sales Qty = 0.
    Separates these completely stagnant items from normal slow-moving Push items.

    Returns DataFrame with all 10 required columns:
      - SKU
      - Description
      - Category
      - Total Stock
      - Inventory Value
      - Aged Qty
      - Aged Value
      - Last Available Sales Information
      - Risk Score
      - Recommended Action

    Plus supporting metadata columns: Item Name, Unit Cost (Rs), Class, Risk Level.
    """
    if items_df is None or items_df.empty:
        return pd.DataFrame(columns=[
            "SKU", "Description", "Category", "Total Stock", "Inventory Value",
            "Aged Qty", "Aged Value", "Last Available Sales Information",
            "Risk Score", "Recommended Action"
        ])

    df = items_df.copy()

    # Identify items where 6M Sales Qty == 0 (or Avg Monthly Sales == 0 and 6M Sales Qty == 0)
    zero_mask = (df["6M Sales Qty"] == 0) | (df["6M Sales Qty"].isna())
    dead_items = df[zero_mask].copy().reset_index(drop=True)

    if dead_items.empty:
        return pd.DataFrame(columns=[
            "SKU", "Description", "Category", "Total Stock", "Inventory Value",
            "Aged Qty", "Aged Value", "Last Available Sales Information",
            "Risk Score", "Recommended Action"
        ])

    # Pre-aggregate last available sales information from sales_df if available
    last_sales_info = {}
    if sales_df is not None and not sales_df.empty:
        valid_sales = sales_df[(sales_df["Qty"] > 0) & (sales_df["Value (Rs)"] > 0)].copy()
        if "Month" in valid_sales.columns:
            ordered_months, _ = parse_and_sort_months(valid_sales["Month"])
            month_rank = {m: i for i, m in enumerate(ordered_months)}

            for sku_val, grp in valid_sales.groupby("SKU"):
                sku_clean = str(sku_val).strip().upper()
                # Find latest transaction by month rank
                if ordered_months:
                    valid_rows = grp[grp["Month"].isin(month_rank)]
                    if not valid_rows.empty:
                        latest_row = valid_rows.loc[valid_rows["Month"].map(month_rank).idxmax()]
                        m_str = str(latest_row["Month"])
                        q_val = float(latest_row["Qty"])
                        v_val = float(latest_row["Value (Rs)"])
                        c_name = str(latest_row.get("CustomerName") or latest_row.get("CustomerID", ""))
                        last_sales_info[sku_clean] = f"Last sale: {m_str} ({int(q_val)} units, ₹{v_val:,.0f} to {c_name})"

            # Also check by Analysis_SKU if present
            if "Analysis_SKU" in valid_sales.columns:
                for a_sku, grp in valid_sales.groupby("Analysis_SKU"):
                    a_clean = str(a_sku).strip().upper()
                    if a_clean not in last_sales_info and ordered_months:
                        valid_rows = grp[grp["Month"].isin(month_rank)]
                        if not valid_rows.empty:
                            latest_row = valid_rows.loc[valid_rows["Month"].map(month_rank).idxmax()]
                            m_str = str(latest_row["Month"])
                            q_val = float(latest_row["Qty"])
                            v_val = float(latest_row["Value (Rs)"])
                            c_name = str(latest_row.get("CustomerName") or latest_row.get("CustomerID", ""))
                            last_sales_info[a_clean] = f"Last sale: {m_str} ({int(q_val)} units, ₹{v_val:,.0f} to {c_name})"

    rows = []
    for _, item in dead_items.iterrows():
        sku = str(item.get("SKU", "")).strip().upper()
        item_name = str(item.get("Item Name") or item.get("Description", sku))
        category = str(item.get("Category", "Unassigned"))
        total_stock = float(item.get("Total Stock", 0.0))
        unit_cost = float(item.get("Unit Cost (Rs)", 0.0))

        inv_val = float(item.get("Inventory Value", 0.0))
        if inv_val <= 0.0 and total_stock > 0 and unit_cost > 0:
            inv_val = total_stock * unit_cost

        aged_qty = float(item.get("Aged Qty", 0.0))
        aged_val = float(item.get("Aged Value", 0.0))
        if aged_val <= 0.0 and aged_qty > 0 and unit_cost > 0:
            aged_val = aged_qty * unit_cost

        risk_score = int(item.get("Risk Score", 0))
        risk_lvl = str(item.get("Risk Level", "Critical"))
        cur_class = str(item.get("Class", "Red List"))

        # Last Available Sales Information
        sales_info = last_sales_info.get(sku, "No sales recorded in 6M review window (Zero historical demand)")

        # Recommended Action
        rec_act = item.get("Recommended Action")
        if not rec_act or pd.isna(rec_act) or str(rec_act).strip() in ["", "nan", "None"]:
            rec_act = generate_dead_stock_action({
                "Total Stock": total_stock,
                "Inventory Value": inv_val,
                "Aged Value": aged_val,
                "Unit Cost (Rs)": unit_cost,
            })

        rows.append({
            "SKU": sku,
            "Description": item_name,
            "Item Name": item_name,
            "Category": category,
            "Total Stock": total_stock,
            "Inventory Value": inv_val,
            "Aged Qty": aged_qty,
            "Aged Value": aged_val,
            "Last Available Sales Information": sales_info,
            "Risk Score": risk_score,
            "Risk Level": risk_lvl,
            "Recommended Action": str(rec_act),
            "Class": cur_class,
            "Unit Cost (Rs)": unit_cost,
            "6M Sales Qty": 0.0,
            "Avg Monthly Sales": 0.0,
            "Months to Clear": float("inf"),
        })

    out_df = pd.DataFrame(rows)

    # Sort strictly by Inventory Value descending
    out_df = out_df.sort_values(
        by=["Inventory Value", "Aged Value"],
        ascending=[False, False]
    ).reset_index(drop=True)

    return out_df


def get_dead_stock_summary(
    dead_stock_df: pd.DataFrame,
    total_inventory_value: float = None,
    total_aged_value: float = None,
) -> dict:
    """
    Computes Dead Stock KPIs and analytical summary metrics.
    """
    if dead_stock_df is None or dead_stock_df.empty:
        return {
            "dead_stock_count": 0,
            "dead_stock_inventory_value": 0.0,
            "dead_stock_aged_value": 0.0,
            "dead_stock_total_units": 0.0,
            "dead_stock_aged_units": 0.0,
            "dead_stock_pct_of_total_inv": 0.0,
            "dead_stock_pct_of_aged_inv": 0.0,
            "high_critical_risk_count": 0,
            "skus": [],
            "kpi_label": "0 SKUs (₹0)",
        }

    count = len(dead_stock_df)
    inv_val = float(dead_stock_df["Inventory Value"].sum())
    aged_val = float(dead_stock_df["Aged Value"].sum())
    tot_units = float(dead_stock_df["Total Stock"].sum())
    aged_units = float(dead_stock_df["Aged Qty"].sum())
    high_crit = int(dead_stock_df["Risk Level"].isin(["Critical", "High"]).sum()) if "Risk Level" in dead_stock_df.columns else count

    pct_inv = (inv_val / total_inventory_value * 100.0) if (total_inventory_value and total_inventory_value > 0) else 0.0
    pct_aged = (aged_val / total_aged_value * 100.0) if (total_aged_value and total_aged_value > 0) else 0.0

    return {
        "dead_stock_count": count,
        "dead_stock_inventory_value": inv_val,
        "dead_stock_aged_value": aged_val,
        "dead_stock_total_units": tot_units,
        "dead_stock_aged_units": aged_units,
        "dead_stock_pct_of_total_inv": pct_inv,
        "dead_stock_pct_of_aged_inv": pct_aged,
        "high_critical_risk_count": high_crit,
        "skus": dead_stock_df["SKU"].tolist(),
        "kpi_label": f"{count} SKU{'s' if count != 1 else ''} (₹{inv_val:,.0f})",
    }


def get_top_dead_stock_by_value(
    dead_stock_df: pd.DataFrame,
    top_n: int = 10,
) -> pd.DataFrame:
    """
    Returns the Top Dead Stock items ranked by Inventory Value descending.
    Preserves exact 10 specified columns.
    """
    if dead_stock_df is None or dead_stock_df.empty:
        return pd.DataFrame(columns=[
            "Rank", "SKU", "Description", "Category", "Total Stock", "Inventory Value",
            "Aged Qty", "Aged Value", "Last Available Sales Information",
            "Risk Score", "Recommended Action"
        ])

    top_df = dead_stock_df.sort_values(
        by=["Inventory Value", "Aged Value"],
        ascending=[False, False]
    ).head(top_n).copy().reset_index(drop=True)

    top_df.insert(0, "Rank", range(1, len(top_df) + 1))

    desired_cols = [
        "Rank", "SKU", "Description", "Category", "Total Stock", "Inventory Value",
        "Aged Qty", "Aged Value", "Last Available Sales Information",
        "Risk Score", "Recommended Action"
    ]
    avail_cols = [c for c in desired_cols if c in top_df.columns]
    return top_df[avail_cols].copy()


def export_dead_stock_excel(dead_stock_df: pd.DataFrame) -> bytes:
    """
    Generates a professionally formatted Excel workbook (.xlsx) for Dead Stock Analysis.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Dead Stock Analysis"

    font_title = Font(name="Calibri", size=14, bold=True, color="0F294A")
    font_sub = Font(name="Calibri", size=9, italic=True, color="475569")
    font_header = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    font_data = Font(name="Calibri", size=9, color="000000")
    header_fill = PatternFill(start_color="991B1B", end_color="991B1B", fill_type="solid")
    border_light = Border(
        left=Side(style="thin", color="E2E8F0"),
        right=Side(style="thin", color="E2E8F0"),
        top=Side(style="thin", color="E2E8F0"),
        bottom=Side(style="thin", color="E2E8F0"),
    )

    ws["A1"] = "Company X — Dead Stock Analysis View (6M Sales Qty = 0)"
    ws["A1"].font = font_title
    ws["A2"] = "Completely Stagnant Inventory Ledger | Analytical Diagnostic (R1-R7 Invariant)"
    ws["A2"].font = font_sub

    ws.row_dimensions[1].height = 22
    ws.row_dimensions[2].height = 16
    ws.row_dimensions[3].height = 10

    export_cols = [
        ("SKU", "SKU"),
        ("Description", "Description"),
        ("Category", "Category"),
        ("Total Stock", "Total Stock"),
        ("Inventory Value", "Inventory Value"),
        ("Aged Qty", "Aged Qty"),
        ("Aged Value", "Aged Value"),
        ("Last Available Sales Information", "Last Available Sales Information"),
        ("Risk Score", "Risk Score"),
        ("Recommended Action", "Recommended Action"),
    ]

    header_row = 4
    ws.row_dimensions[header_row].height = 24

    for col_idx, (col_title, _) in enumerate(export_cols, start=1):
        cell = ws.cell(row=header_row, column=col_idx, value=col_title)
        cell.font = font_header
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border_light

    if dead_stock_df is not None and not dead_stock_df.empty:
        for r_idx, (_, row) in enumerate(dead_stock_df.iterrows(), start=header_row + 1):
            ws.row_dimensions[r_idx].height = 20
            for c_idx, (_, df_col) in enumerate(export_cols, start=1):
                val = row.get(df_col, "")
                cell = ws.cell(row=r_idx, column=c_idx)
                cell.font = font_data
                cell.border = border_light

                if df_col in ["Inventory Value", "Aged Value"]:
                    cell.value = float(val) if pd.notna(val) else 0.0
                    cell.number_format = "₹#,##0"
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                elif df_col in ["Total Stock", "Aged Qty"]:
                    cell.value = float(val) if pd.notna(val) else 0.0
                    cell.number_format = "#,##0"
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                elif df_col in ["Risk Score"]:
                    cell.value = int(val) if pd.notna(val) else 0
                    cell.number_format = "0"
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                elif df_col == "SKU":
                    cell.value = str(val) if pd.notna(val) else ""
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                else:
                    cell.value = str(val) if pd.notna(val) else ""
                    cell.alignment = Alignment(horizontal="left", vertical="center")

    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = 0
        for cell in col:
            if cell.row < header_row:
                continue
            v = str(cell.value or "")
            if len(v) > max_len:
                max_len = len(v)
        ws.column_dimensions[col_letter].width = min(max(max_len + 3, 11), 50)

    ws.freeze_panes = "A5"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
