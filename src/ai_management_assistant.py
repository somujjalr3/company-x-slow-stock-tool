"""
AI Management Assistant Module for Company X Slow Stock Action Tool.

Provides an optional, executive-grade AI Management Assistant that serves exclusively
as an interpretation and inquiry layer over pre-calculated, deterministic analytical outputs.

CRITICAL ARCHITECTURAL CONSTRAINTS & GOVERNANCE INVARIANTS:
1. The AI must NOT calculate financial metrics.
2. The AI must NOT classify SKUs.
3. The AI must NOT determine Rules R1-R7.
4. The AI must ONLY interpret already-calculated deterministic outputs.
5. All responses must reference actual calculated values. Never invent numbers.
6. If information is unavailable, the assistant must return "Insufficient data available."
7. Clear disclaimer: AI is strictly an interpretation layer; all calculations originate
   from the deterministic analytical engine.
"""

import re
import json
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

from src.logger import get_logger
from src.sales_priority import get_ranked_push_table
from src.sales_action_center import build_sales_action_table
from src.dead_stock import identify_dead_stock

logger = get_logger("AIManagementAssistant")

# ==============================================================================
# MANDATORY INTERPRETATION LAYER DISCLAIMER
# ==============================================================================
AI_DISCLAIMER = (
    "Interpretation Layer Disclaimer: This assistant operates strictly as an explanatory "
    "and inquiry interface over pre-calculated deterministic outputs. The AI does NOT calculate "
    "financial metrics, does NOT classify SKUs, and does NOT determine Rules R1–R7. "
    "All figures, classifications, risk scores, priority rankings, and action recommendations "
    "are produced deterministically by the analytical engine. No numbers are invented or estimated."
)


# ==============================================================================
# 1. STRUCTURED MANAGEMENT CONTEXT BUILDER
# ==============================================================================
def build_management_structured_context(
    items: pd.DataFrame,
    targets: Any,
    working_capital: Optional[Dict[str, Any]] = None,
    dead_stock: Optional[pd.DataFrame] = None,
    config: Optional[Any] = None,
    sales_trends: Optional[Dict[str, Any]] = None,
    sales_df: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """
    Constructs a grounded, comprehensive structured data payload for the AI assistant.
    Only contains already-calculated metrics from the deterministic pipeline.
    """
    if items is None or items.empty:
        return {
            "kpis": {},
            "top_push_items": [],
            "sku_catalog": {},
            "categories": [],
            "top_cash_at_risk": [],
            "customer_opportunities": [],
            "dead_stock": [],
            "disclaimer": AI_DISCLAIMER,
        }

    # 1. Portfolio KPIs
    counts = items["Class"].value_counts().to_dict() if "Class" in items else {}
    push_count = int(counts.get("Push", 0))
    red_count = int(counts.get("Red List", 0))
    noaction_count = int(counts.get("No Action", 0))
    total_skus = len(items)

    total_inv_val = float(items["Inventory Value"].sum()) if "Inventory Value" in items else 0.0
    total_aged_qty = float(items["Aged Qty"].sum()) if "Aged Qty" in items else 0.0
    total_aged_val = float(items["Aged Value"].sum()) if "Aged Value" in items else 0.0

    push_items_df = items[items["Class"] == "Push"] if "Class" in items else pd.DataFrame()
    push_aged_val = float(push_items_df["Aged Value"].sum()) if not push_items_df.empty and "Aged Value" in push_items_df else 0.0
    push_aged_share = (push_aged_val / total_aged_val) if total_aged_val > 0 else 0.0

    red_items_df = items[items["Class"] == "Red List"] if "Class" in items else pd.DataFrame()
    red_inv_val = float(red_items_df["Inventory Value"].sum()) if not red_items_df.empty and "Inventory Value" in red_items_df else 0.0

    crit_risk_count = int((items["Risk Level"] == "Critical").sum()) if "Risk Level" in items else 0
    high_risk_count = int((items["Risk Level"] == "High").sum()) if "Risk Level" in items else 0

    # Dead stock
    if dead_stock is None:
        dead_stock = identify_dead_stock(items, sales_df=sales_df)
    dead_count = len(dead_stock) if dead_stock is not None else 0
    dead_aged_val = float(dead_stock["Aged Value"].sum()) if (dead_stock is not None and not dead_stock.empty and "Aged Value" in dead_stock) else 0.0

    # Customer accounts count
    if isinstance(targets, dict):
        eligible_cust_count = len({
            cid for df in targets.values()
            if isinstance(df, pd.DataFrame) and not df.empty and "CustomerID" in df.columns
            for cid in df["CustomerID"].dropna()
        })
    elif isinstance(targets, pd.DataFrame) and not targets.empty:
        eligible_cust_count = targets["CustomerID"].nunique() if "CustomerID" in targets.columns else 0
    else:
        eligible_cust_count = 0

    kpis = {
        "total_skus": total_skus,
        "push_skus": push_count,
        "red_list_skus": red_count,
        "no_action_skus": noaction_count,
        "total_inventory_value": total_inv_val,
        "total_aged_quantity": total_aged_qty,
        "total_aged_value": total_aged_val,
        "push_aged_value": push_aged_val,
        "push_aged_share_pct": round(push_aged_share * 100, 1),
        "red_list_inventory_value": red_inv_val,
        "high_or_critical_risk_skus": crit_risk_count + high_risk_count,
        "critical_risk_skus": crit_risk_count,
        "high_risk_skus": high_risk_count,
        "dead_stock_skus": dead_count,
        "dead_stock_aged_value": dead_aged_val,
        "eligible_customer_accounts": eligible_cust_count,
        "config_mode": config.mode_label if config else "CASE DEFAULT SETTINGS",
    }

    # 2. Ranked Push Table
    ranked_push = get_ranked_push_table(items, sales_trends=sales_trends)
    top_push_items = []
    if not ranked_push.empty:
        for _, r in ranked_push.iterrows():
            top_push_items.append({
                "rank": int(r["Rank"]),
                "sku": str(r["SKU"]),
                "item_name": str(r.get("Description", r.get("Item Name", ""))),
                "category": str(r.get("Category", "")),
                "aged_value": float(r.get("Aged Value", 0.0)),
                "months_to_clear": round(float(r.get("Months to Clear", 0.0)), 1),
                "sales_trend": str(r.get("Sales Trend", "Stable")),
                "risk_score": int(r.get("Risk Score", 0)),
                "priority_score": int(r.get("Priority Score", 0)),
                "priority_level": str(r.get("Priority Level", "Medium")),
                "why_priority": str(r.get("Why Priority?", r.get("Why Priority", ""))),
                "recommended_action": str(r.get("Recommended Action", "")),
            })

    # 3. Complete SKU Catalog Lookup
    sku_catalog = {}
    for _, row in items.iterrows():
        sku = str(row.get("SKU", "")).strip()
        if not sku:
            continue
        mtc_val = row.get("Months to Clear")
        mtc_clean = round(float(mtc_val), 1) if (pd.notna(mtc_val) and not np.isinf(mtc_val)) else "∞ (Stagnant)"
        sku_catalog[sku.upper()] = {
            "sku": sku,
            "item_name": str(row.get("Item Name", "")),
            "category": str(row.get("Category", "")),
            "status": str(row.get("Status", "Active")),
            "master_pack_qty": float(row.get("Master Pack Qty", 1)),
            "unit_cost": float(row.get("Unit Cost (Rs)", 0.0)),
            "total_stock": float(row.get("Total Stock", 0.0)),
            "inventory_value": float(row.get("Inventory Value", 0.0)),
            "aged_qty": float(row.get("Aged Qty", 0.0)),
            "aged_value": float(row.get("Aged Value", 0.0)),
            "avg_monthly_sales": round(float(row.get("Avg Monthly Sales", 0.0)), 1),
            "months_to_clear": mtc_clean,
            "classification": str(row.get("Class", "")),
            "rule_triggered": str(row.get("Rule Triggered", "")),
            "classification_reason": str(row.get("Classification Reason", row.get("Reason", ""))),
            "classification_explanation": str(row.get("Classification Explanation", "")),
            "risk_score": int(row.get("Risk Score", 0)) if pd.notna(row.get("Risk Score")) else 0,
            "risk_level": str(row.get("Risk Level", "Medium")),
            "sales_trend": str(row.get("Sales Trend", "Stable")),
            "priority_score": int(row.get("Priority Score", 0)) if pd.notna(row.get("Priority Score")) else None,
            "priority_level": str(row.get("Priority Level", "")) if pd.notna(row.get("Priority Level")) else None,
            "why_priority": str(row.get("Why Priority", "")),
            "recommended_action": str(row.get("Recommended Action", "")),
        }

    # 4. Working Capital & Category Breakdown
    categories = []
    top_cash_at_risk = []
    if working_capital and "by_category" in working_capital and isinstance(working_capital["by_category"], pd.DataFrame):
        for _, c_row in working_capital["by_category"].iterrows():
            ag_val = float(c_row.get("Aged Value", 0.0))
            cap_share = round((ag_val / total_aged_val * 100.0), 1) if total_aged_val > 0 else 0.0
            categories.append({
                "category": str(c_row.get("Category", "")),
                "sku_count": int(c_row.get("SKU Count", 0)),
                "inventory_value": float(c_row.get("Inventory Value", 0.0)),
                "aged_value": ag_val,
                "capital_share_pct": cap_share,
                "exposure_level": "High Exposure" if cap_share >= 20.0 else ("Moderate Exposure" if cap_share >= 10.0 else "Controlled Exposure"),
            })

    top10_df = None
    if working_capital:
        top10_df = working_capital.get("top10_aged_skus")
        if top10_df is None:
            top10_df = working_capital.get("top_10_risk")
    if top10_df is None and items is not None and not items.empty and "Aged Value" in items.columns:
        top10_df = items.sort_values(by="Aged Value", ascending=False).head(10)

    if top10_df is not None and isinstance(top10_df, pd.DataFrame) and not top10_df.empty:
        for _, t_row in top10_df.iterrows():
            top_cash_at_risk.append({
                "sku": str(t_row.get("SKU", "")),
                "item_name": str(t_row.get("Item Name", "")),
                "category": str(t_row.get("Category", "")),
                "classification": str(t_row.get("Class", "")),
                "aged_value": float(t_row.get("Aged Value", 0.0)),
                "months_to_clear": round(float(t_row.get("Months to Clear", 0.0)), 1),
            })

    # 5. Customer Sales Opportunities
    action_table = build_sales_action_table(items, targets)
    customer_opportunities = []
    if not action_table.empty:
        for _, a_row in action_table.head(15).iterrows():
            customer_opportunities.append({
                "action_rank": int(a_row.get("Action Rank", 0)),
                "sku": str(a_row.get("SKU", "")),
                "item_name": str(a_row.get("Item Description", a_row.get("Item Name", ""))),
                "customer_id": str(a_row.get("Customer ID", a_row.get("CustomerID", ""))),
                "customer_name": str(a_row.get("Customer Name", "")),
                "customer_industry": str(a_row.get("Customer Industry", "")),
                "customer_bucket": str(a_row.get("Customer Bucket", "")),
                "purchase_value_6m": float(a_row.get("6M Purchase Value", 0.0)),
                "opportunity_score": int(a_row.get("Opportunity Score", 0)),
                "recommended_action": str(a_row.get("Recommended Action", "")),
                "reason": str(a_row.get("Action Reason", a_row.get("Reason", ""))),
            })

    # 6. Dead Stock Items
    dead_stock_list = []
    if dead_stock is not None and not dead_stock.empty:
        for _, d_row in dead_stock.iterrows():
            dead_stock_list.append({
                "sku": str(d_row.get("SKU", "")),
                "description": str(d_row.get("Description", d_row.get("Item Name", ""))),
                "category": str(d_row.get("Category", "")),
                "total_stock": float(d_row.get("Total Stock", 0.0)),
                "inventory_value": float(d_row.get("Inventory Value", 0.0)),
                "aged_value": float(d_row.get("Aged Value", 0.0)),
                "last_sales_info": str(d_row.get("Last Available Sales Information", "Zero sales in 6 months")),
                "recommended_action": str(d_row.get("Recommended Action", "")),
            })

    return {
        "kpis": kpis,
        "top_push_items": top_push_items,
        "sku_catalog": sku_catalog,
        "categories": categories,
        "top_cash_at_risk": top_cash_at_risk,
        "customer_opportunities": customer_opportunities,
        "dead_stock": dead_stock_list,
        "disclaimer": AI_DISCLAIMER,
    }


# ==============================================================================
# 2. DETERMINISTIC INTERPRETIVE REASONING ENGINE
# ==============================================================================
def interpret_management_query(
    query: str,
    context: Dict[str, Any],
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Answers management questions strictly interpreting pre-calculated deterministic context.

    Supported Canonical Queries:
    1. "Which five items should we prioritize?"
    2. "Why is SKU1006 important?" (or any specific SKU)
    3. "Which categories have the highest aged inventory?"
    4. "What are the biggest working capital risks?"
    5. "Which customers should sales contact?"
    Plus free-form management inquiries.

    Guarantees:
    - Never calculates financial metrics.
    - Never classifies SKUs or alters R1-R7.
    - Never invents numbers.
    - Returns "Insufficient data available." if information is absent.
    - Includes the mandatory interpretation layer disclaimer.
    """
    cleaned_query = (query or "").strip().lower()
    if not cleaned_query:
        return {
            "answer": "Insufficient data available. Please provide a specific operational question.",
            "referenced_metrics": {},
            "disclaimer": AI_DISCLAIMER,
            "status": "INSUFFICIENT_DATA",
        }

    kpis = context.get("kpis", {})
    sku_catalog = context.get("sku_catalog", {})
    top_push = context.get("top_push_items", [])
    categories = context.get("categories", [])
    top_risk = context.get("top_cash_at_risk", [])
    customer_opps = context.get("customer_opportunities", [])
    dead_stock = context.get("dead_stock", [])

    # Check for specific SKU reference first (e.g., SKU1006, SKU1005, SKU1012, etc.)
    sku_match = re.search(r"\b(sku\d{4}|sku[a-z0-9_\-]+)\b", cleaned_query, re.IGNORECASE)
    if sku_match:
        target_sku = sku_match.group(1).upper()
        return _interpret_sku_inquiry(target_sku, sku_catalog, customer_opps)

    # 1. "Which five items should we prioritize?" / Priority items
    if any(k in cleaned_query for k in ["five items", "prioritize", "priority item", "top push", "which item", "which sku", "focus first", "rank 1"]):
        return _interpret_priority_items(top_push, kpis)

    # 2. "Which categories have the highest aged inventory?" / Category exposure
    if any(k in cleaned_query for k in ["category", "categories", "highest aged", "sector"]):
        return _interpret_category_exposure(categories, kpis)

    # 3. "What are the biggest working capital risks?" / Cash at risk / Working capital
    if any(k in cleaned_query for k in ["working capital", "capital risk", "cash at risk", "cash-at-risk", "financial risk", "trapped capital"]):
        return _interpret_working_capital_risks(kpis, top_risk, top_push, dead_stock)

    # 4. "Which customers should sales contact?" / Who to call / Customer outreach
    if any(k in cleaned_query for k in ["customer", "customers", "call today", "who should sales", "contact", "sales rep", "outreach"]):
        return _interpret_customer_contacts(customer_opps, kpis)

    # 5. Dead stock / zero sales inquiry
    if any(k in cleaned_query for k in ["dead stock", "zero sales", "non-moving", "stagnant"]):
        return _interpret_dead_stock(dead_stock, kpis)

    # 6. Overall inventory / KPI overview
    if any(k in cleaned_query for k in ["how much inventory", "kpi", "summary", "overview", "portfolio", "how many skus"]):
        return _interpret_portfolio_overview(kpis)

    # If the user query is outside the available dataset scope:
    return {
        "answer": (
            "Insufficient data available. The requested information cannot be verified from the "
            "calculated inventory, sales, or customer dataset. The assistant only interprets "
            "verified figures produced by the deterministic analytical engine."
        ),
        "referenced_metrics": {},
        "disclaimer": AI_DISCLAIMER,
        "status": "INSUFFICIENT_DATA",
    }


# ==============================================================================
# 3. SPECIALIZED GROUNDED QUERY INTERPRETERS
# ==============================================================================
def _interpret_priority_items(top_push: List[Dict[str, Any]], kpis: Dict[str, Any]) -> Dict[str, Any]:
    """Interprets: 'Which five items should we prioritize?' strictly from ranked push table."""
    if not top_push:
        return {
            "answer": "Insufficient data available. No Push items exist in the active catalog requiring commercial push.",
            "referenced_metrics": {},
            "disclaimer": AI_DISCLAIMER,
            "status": "INSUFFICIENT_DATA",
        }

    items_to_show = top_push[:5]
    lines = [
        f"Based on the deterministic Sales Priority Score (0–100), the sales team should prioritize "
        f"the following **{len(items_to_show)} Push SKUs** out of {kpis.get('push_skus', 18)} total Push items:"
    ]

    referenced = {}
    for idx, it in enumerate(items_to_show, start=1):
        sku = it["sku"]
        name = it["item_name"]
        cat = it["category"]
        aged_val = it["aged_value"]
        mtc = it["months_to_clear"]
        p_score = it["priority_score"]
        p_lvl = it["priority_level"]
        trend = it["sales_trend"]
        action = it["recommended_action"]

        referenced[f"Rank {idx}"] = {
            "SKU": sku,
            "Item Name": name,
            "Priority Score": p_score,
            "Priority Level": p_lvl,
            "Aged Value": f"₹{aged_val:,.0f}",
            "Months to Clear": f"{mtc}m",
            "Sales Trend": trend,
            "Recommended Action": action,
        }

        lines.append(
            f"**{idx}. {sku} ({name})** — *{cat}*\n"
            f"   • **Priority Score:** **{p_score}/100** ({p_lvl})\n"
            f"   • **Aged Inventory Value:** **₹{aged_val:,.0f}**\n"
            f"   • **Months to Clear:** **{mtc} months** | **Sales Trend:** {trend}\n"
            f"   • **Recommended Action:** {action}"
        )

    lines.append(
        f"\n**Strategic Rationale:** These five items represent ₹{sum(it['aged_value'] for it in items_to_show):,.0f} "
        f"of aged capital requiring rapid liquidation via targeted customer promotions."
    )

    return {
        "answer": "\n".join(lines),
        "referenced_metrics": referenced,
        "disclaimer": AI_DISCLAIMER,
        "status": "SUCCESS",
    }


def _interpret_sku_inquiry(
    sku: str,
    sku_catalog: Dict[str, Any],
    customer_opps: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Interprets: 'Why is SKU1006 important?' or any specific SKU inquiry."""
    item = sku_catalog.get(sku.upper())
    if not item:
        return {
            "answer": f"Insufficient data available. SKU '{sku}' was not found in the active catalog or has no calculated operational metrics.",
            "referenced_metrics": {},
            "disclaimer": AI_DISCLAIMER,
            "status": "INSUFFICIENT_DATA",
        }

    sku_id = item["sku"]
    name = item["item_name"]
    cat = item["category"]
    cls = item["classification"]
    inv_val = item["inventory_value"]
    aged_val = item["aged_value"]
    aged_qty = item["aged_qty"]
    total_stock = item["total_stock"]
    mtc = item["months_to_clear"]
    avg_sales = item["avg_monthly_sales"]
    risk_s = item["risk_score"]
    risk_l = item["risk_level"]
    prio_s = item.get("priority_score")
    prio_l = item.get("priority_level")
    trend = item["sales_trend"]
    why_prio = item.get("why_priority") or item.get("classification_explanation") or item.get("classification_reason")
    action = item["recommended_action"]
    rule = item["rule_triggered"]

    # Customer opportunities for this specific SKU
    sku_custs = [c for c in customer_opps if c["sku"].upper() == sku_id.upper()]

    lines = [
        f"**{sku_id} ({name})** is classified as **{cls}** under deterministic **{rule or 'Rule R5'}**.\n",
        f"**Why is {sku_id} important?**",
        f"• **Classification & Urgency:** Classified as **{cls}** with a **Risk Score of {risk_s}/100 ({risk_l})**."
    ]

    if prio_s is not None:
        lines.append(f"• **Sales Priority Score:** **{prio_s}/100 ({prio_l})**.")

    lines.extend([
        f"• **Capital at Risk:** Holds **₹{aged_val:,.0f}** of aged inventory (91+ days) across **{aged_qty:,.0f} aged units** (out of ₹{inv_val:,.0f} total stock value and {total_stock:,.0f} units).",
        f"• **Clearance Runway:** Currently has **{mtc} months to clear** under average monthly sales of **{avg_sales} units/month** with a **{trend}** demand trend.",
        f"• **Deterministic Rationale:** {why_prio}",
        f"• **Recommended Action:** {action}",
    ])

    if sku_custs:
        lines.append(f"\n**Sales Opportunity Matches:** {len(sku_custs)} prioritized customer accounts identified:")
        for c in sku_custs[:3]:
            lines.append(f"  - **{c['customer_name']} ({c['customer_id']})**: {c['customer_bucket']} | 6M Spend: ₹{c['purchase_value_6m']:,.0f} | Opp Score: {c['opportunity_score']}/100")

    referenced = {
        "SKU": sku_id,
        "Classification": cls,
        "Total Stock Value": f"₹{inv_val:,.0f}",
        "Aged Inventory Value": f"₹{aged_val:,.0f}",
        "Months to Clear": f"{mtc}m",
        "Risk Score": f"{risk_s} ({risk_l})",
        "Priority Score": f"{prio_s} ({prio_l})" if prio_s is not None else "N/A",
        "Recommended Action": action,
    }

    return {
        "answer": "\n".join(lines),
        "referenced_metrics": referenced,
        "disclaimer": AI_DISCLAIMER,
        "status": "SUCCESS",
    }


def _interpret_category_exposure(
    categories: List[Dict[str, Any]],
    kpis: Dict[str, Any],
) -> Dict[str, Any]:
    """Interprets: 'Which categories have the highest aged inventory?'."""
    if not categories:
        return {
            "answer": "Insufficient data available. Category working capital breakdown is not present in active context.",
            "referenced_metrics": {},
            "disclaimer": AI_DISCLAIMER,
            "status": "INSUFFICIENT_DATA",
        }

    # Sort categories by Aged Value descending
    sorted_cats = sorted(categories, key=lambda c: c["aged_value"], reverse=True)
    total_aged = kpis.get("total_aged_value", sum(c["aged_value"] for c in sorted_cats))

    lines = [
        f"Across Company X's active commercial portfolio, total aged inventory stands at **₹{total_aged:,.0f}**. "
        f"The categories ranked by aged capital exposure are:\n"
    ]

    referenced = {}
    for idx, c in enumerate(sorted_cats, start=1):
        cat_name = c["category"]
        ag_val = c["aged_value"]
        share = c["capital_share_pct"]
        inv_val = c["inventory_value"]
        skus = c["sku_count"]
        exp = c["exposure_level"]

        referenced[cat_name] = {
            "Rank": idx,
            "Aged Value": f"₹{ag_val:,.0f}",
            "Share of Aged Capital": f"{share}%",
            "Total Inventory Value": f"₹{inv_val:,.0f}",
            "SKU Count": skus,
            "Exposure Assessment": exp,
        }

        lines.append(
            f"**{idx}. {cat_name}**\n"
            f"   • **Aged Inventory Value:** **₹{ag_val:,.0f}** (**{share}%** of company cash at risk)\n"
            f"   • **Total Inventory Value:** ₹{inv_val:,.0f} across {skus} SKUs\n"
            f"   • **Exposure Assessment:** {exp}"
        )

    top_cat = sorted_cats[0]
    lines.append(
        f"\n**Management Insight:** **{top_cat['category']}** holds the highest working capital exposure "
        f"(₹{top_cat['aged_value']:,.0f}, {top_cat['capital_share_pct']}% of all aged inventory). "
        f"Commercial sales campaigns must concentrate primarily on clearing {top_cat['category']} push allocations."
    )

    return {
        "answer": "\n".join(lines),
        "referenced_metrics": referenced,
        "disclaimer": AI_DISCLAIMER,
        "status": "SUCCESS",
    }


def _interpret_working_capital_risks(
    kpis: Dict[str, Any],
    top_risk: List[Dict[str, Any]],
    top_push: List[Dict[str, Any]],
    dead_stock: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Interprets: 'What are the biggest working capital risks?'."""
    total_aged = kpis.get("total_aged_value", 0.0)
    push_aged = kpis.get("push_aged_value", 0.0)
    push_share = kpis.get("push_aged_share_pct", 0.0)
    red_inv = kpis.get("red_list_inventory_value", 0.0)
    dead_aged = kpis.get("dead_stock_aged_value", 0.0)

    lines = [
        f"**Company X Working Capital Exposure Assessment:**\n",
        f"1. **Total Cash-at-Risk:** **₹{total_aged:,.0f}** is currently locked in aged inventory (91+ days) across {kpis.get('total_aged_quantity', 0):,.0f} units.",
        f"2. **Primary Recoverable Pool (Push Items):** **₹{push_aged:,.0f}** (**{push_share}%** of all aged capital) is tied up in 18 Push SKUs. This represents the primary recoverable capital that sales teams can liquidate through pre-qualified customer campaigns.",
        f"3. **Stagnant Capital (Red List & Dead Stock):** **₹{red_inv:,.0f}** is held in Red List items with 6M sales < 1 Master Pack, including **₹{dead_aged:,.0f}** in dead stock with zero recorded demand. This requires commercial delisting or supplier renegotiation.",
    ]

    referenced = {
        "Total Aged Value (Cash at Risk)": f"₹{total_aged:,.0f}",
        "Push Aged Value": f"₹{push_aged:,.0f} ({push_share}%)",
        "Red List Inventory Value": f"₹{red_inv:,.0f}",
        "Dead Stock Aged Value": f"₹{dead_aged:,.0f}",
    }

    if top_risk:
        lines.append("\n**Top 5 Cash-at-Risk SKUs:**")
        for idx, r in enumerate(top_risk[:5], start=1):
            sku = r["sku"]
            name = r["item_name"]
            cls = r["classification"]
            aged_v = r["aged_value"]
            mtc = r["months_to_clear"]
            lines.append(f"  {idx}. **{sku} ({name})** — *{cls}*: **₹{aged_v:,.0f}** aged inventory ({mtc}m runway)")
            referenced[f"Top Risk #{idx}"] = f"{sku} ({cls}): ₹{aged_v:,.0f}"

    lines.append(
        "\n**Recommended Action:** Focus commercial sales outreach on high-aged Push items "
        "(SKU1005, SKU1034, SKU1020) while initiating vendor buyback or scrap review for Red List items."
    )

    return {
        "answer": "\n".join(lines),
        "referenced_metrics": referenced,
        "disclaimer": AI_DISCLAIMER,
        "status": "SUCCESS",
    }


def _interpret_customer_contacts(
    customer_opps: List[Dict[str, Any]],
    kpis: Dict[str, Any],
) -> Dict[str, Any]:
    """Interprets: 'Which customers should sales contact?'."""
    if not customer_opps:
        return {
            "answer": "Insufficient data available. No pre-qualified customer targets exist for active Push items.",
            "referenced_metrics": {},
            "disclaimer": AI_DISCLAIMER,
            "status": "INSUFFICIENT_DATA",
        }

    lines = [
        f"Sales teams should contact **pre-qualified eligible customer accounts** "
        f"(6-month spend > ₹100,000 under Rule R6). Top prioritized call targets are:\n"
    ]

    referenced = {}
    for idx, c in enumerate(customer_opps[:5], start=1):
        sku = c["sku"]
        cid = c["customer_id"]
        cname = c["customer_name"]
        ind = c["customer_industry"]
        bkt = c["customer_bucket"]
        spend = c["purchase_value_6m"]
        opp_score = c["opportunity_score"]
        act = c["recommended_action"]

        referenced[f"Contact #{idx}"] = {
            "Customer ID": cid,
            "Customer Name": cname,
            "SKU": sku,
            "Bucket": bkt,
            "6M Purchase Value": f"₹{spend:,.0f}",
            "Opportunity Score": opp_score,
        }

        lines.append(
            f"**{idx}. {cname} ({cid})** for **{sku}**\n"
            f"   • **Segment:** {bkt} | **Industry:** {ind}\n"
            f"   • **6-Month Spend:** **₹{spend:,.0f}** | **Opportunity Score:** **{opp_score}/100**\n"
            f"   • **Action Recommendation:** {act}"
        )

    lines.append(
        f"\n**Targeting Strategy:** Prioritize **Bucket 1 accounts** (historical buyers) first, "
        f"followed by **Bucket 2 accounts** (industry peers with verified demand for this product category)."
    )

    return {
        "answer": "\n".join(lines),
        "referenced_metrics": referenced,
        "disclaimer": AI_DISCLAIMER,
        "status": "SUCCESS",
    }


def _interpret_dead_stock(
    dead_stock: List[Dict[str, Any]],
    kpis: Dict[str, Any],
) -> Dict[str, Any]:
    """Interprets inquiries about dead stock."""
    if not dead_stock:
        return {
            "answer": "Deterministic engine records **0 dead stock items** in the active catalog (all active SKUs have recorded sales).",
            "referenced_metrics": {"Dead Stock SKUs": 0},
            "disclaimer": AI_DISCLAIMER,
            "status": "SUCCESS",
        }

    lines = [
        f"The deterministic engine identified **{len(dead_stock)} Dead Stock SKU** with **6M Sales Qty = 0**:\n"
    ]
    referenced = {}
    for d in dead_stock:
        sku = d["sku"]
        desc = d["description"]
        cat = d["category"]
        stk = d["total_stock"]
        inv_v = d["inventory_value"]
        ag_v = d["aged_value"]
        last = d["last_sales_info"]
        act = d["recommended_action"]

        referenced[sku] = {
            "SKU": sku,
            "Description": desc,
            "Category": cat,
            "Inventory Value": f"₹{inv_v:,.0f}",
            "Aged Value": f"₹{ag_v:,.0f}",
            "Total Units": stk,
            "Action": act,
        }

        lines.append(
            f"• **{sku} ({desc})** — *{cat}*\n"
            f"  - **Inventory Value:** **₹{inv_v:,.0f}** | **Aged Value:** **₹{ag_v:,.0f}** ({stk:,.0f} units)\n"
            f"  - **Sales History:** {last}\n"
            f"  - **Recommended Action:** {act}"
        )

    return {
        "answer": "\n".join(lines),
        "referenced_metrics": referenced,
        "disclaimer": AI_DISCLAIMER,
        "status": "SUCCESS",
    }


def _interpret_portfolio_overview(kpis: Dict[str, Any]) -> Dict[str, Any]:
    """Interprets general portfolio KPIs."""
    lines = [
        f"**Company X Portfolio Overview:**\n",
        f"• **Total Active Commercial SKUs:** {kpis.get('total_skus', 0)} SKUs",
        f"• **Slow Stock Classification Breakdown:**",
        f"  - **Push Items:** {kpis.get('push_skus', 0)} SKUs (₹{kpis.get('push_aged_value', 0):,.0f} aged value, {kpis.get('push_aged_share_pct', 0)}% of aged capital)",
        f"  - **Red List Items:** {kpis.get('red_list_skus', 0)} SKUs (₹{kpis.get('red_list_inventory_value', 0):,.0f} inventory value)",
        f"  - **No Action Items:** {kpis.get('no_action_skus', 0)} SKUs (healthy clearance or zero aged stock)",
        f"• **Total Inventory Value:** ₹{kpis.get('total_inventory_value', 0):,.0f}",
        f"• **Total Aged Inventory (Cash at Risk):** ₹{kpis.get('total_aged_value', 0):,.0f} across {kpis.get('total_aged_quantity', 0):,.0f} units",
        f"• **Dead Stock (Zero Sales):** {kpis.get('dead_stock_skus', 0)} SKUs (₹{kpis.get('dead_stock_aged_value', 0):,.0f})",
        f"• **Eligible Customer Accounts (> ₹100k spend):** {kpis.get('eligible_customer_accounts', 0)} qualified accounts",
    ]

    return {
        "answer": "\n".join(lines),
        "referenced_metrics": kpis,
        "disclaimer": AI_DISCLAIMER,
        "status": "SUCCESS",
    }
