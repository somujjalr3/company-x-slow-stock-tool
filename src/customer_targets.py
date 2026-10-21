"""
Customer Targeting and Opportunity Scoring Module for Company X Slow Stock Action Tool.

R6 & R7 CUSTOMER TARGETING:

Eligible customers:
  6-month purchase value > ₹100,000.

Bucket 1:
  Customers who previously bought the Push SKU or its switch partner.

Bucket 2:
  Remaining eligible customers whose Industry matches an Industry
  associated with customers who previously bought the Push SKU.
  Customers with missing Industry cannot enter Bucket 2.

Bucket 3:
  Remaining eligible customers who bought another item from the same Category.

R7 Sorting:
  Bucket ascending, then 6-month purchase value descending.
  Deterministic tie-breaking on CustomerID.

CUSTOMER OPPORTUNITY SCORE (0-100):
  Deterministic multi-factor score evaluating account readiness and conversion opportunity:
  1. Item / Switch / Industry / Category Affinity (Max 35 pts)
  2. Customer 6M Spend Scale (Max 25 pts)
  3. Category Purchase Depth & History (Max 20 pts)
  4. Purchase Recency (Max 20 pts)

CONSTRAINTS & INVARIANTS:
  - Do NOT modify R6 or R7.
  - Bucket 1, Bucket 2, Bucket 3 remain exactly as defined.
  - Opportunity Score must NEVER move a customer between buckets or override R7 sorting.
  - 100% deterministic, explainable calculations without AI.
"""

from typing import Dict, List, Tuple, Any, Optional
import numpy as np
import pandas as pd
from src.logger import get_logger

logger = get_logger("CustomerTargets")

from src.sales_trends import parse_and_sort_months
from src.config import CaseConfig, get_default_config


def calculate_customer_opportunity_score(
    spend,
    bucket,
    bought_exact,
    bought_switch,
    category_spend,
    recency_gap=None,
):
    """
    Deterministic 0-100 Customer Opportunity Score.

    Parameters:
      spend (float): Total 6-month purchase value for this customer across all items.
      bucket (int): R6 Bucket assignment (1, 2, or 3).
      bought_exact (bool): Whether customer purchased the exact Push SKU.
      bought_switch (bool): Whether customer purchased a SWITCH partner of the Push SKU.
      category_spend (float): Total 6-month spend by customer in this item's category.
      recency_gap (int or None): Chronological months since customer's most recent purchase
                                 (0 = most recent/active month, 1 = 1 month ago, etc.).

    Returns:
      tuple of (score: int, level: str, breakdown: dict)
    """
    # 1. Affinity (Max 35 pts)
    if bought_exact:
        aff_pts = 35
    elif bought_switch:
        aff_pts = 30
    elif bucket == 2:
        aff_pts = 18
    elif bucket == 3:
        aff_pts = 12
    else:
        aff_pts = 5

    # 2. 6M Spend Scale (Max 25 pts)
    spend_val = float(spend) if pd.notna(spend) else 0.0
    if spend_val >= 750000:
        spend_pts = 25
    elif spend_val >= 500000:
        spend_pts = 20
    elif spend_val >= 300000:
        spend_pts = 16
    elif spend_val >= 200000:
        spend_pts = 12
    elif spend_val >= 150000:
        spend_pts = 8
    else:
        spend_pts = 5  # Base score for eligible accounts (> 100k)

    # 3. Category Purchase Depth (Max 20 pts)
    cat_val = float(category_spend) if pd.notna(category_spend) else 0.0
    if cat_val >= 150000:
        cat_pts = 20
    elif cat_val >= 100000:
        cat_pts = 16
    elif cat_val >= 50000:
        cat_pts = 12
    elif cat_val >= 20000:
        cat_pts = 8
    elif cat_val > 0:
        cat_pts = 4
    else:
        cat_pts = 0

    # 4. Purchase Recency (Max 20 pts)
    if recency_gap is not None:
        if recency_gap == 0:
            rec_pts = 20
        elif recency_gap == 1:
            rec_pts = 15
        elif recency_gap == 2:
            rec_pts = 10
        elif recency_gap == 3:
            rec_pts = 6
        else:
            rec_pts = 3
    else:
        rec_pts = 10  # Neutral fallback when dates are unavailable

    total_pts = int(round(min(100, max(0, aff_pts + spend_pts + cat_pts + rec_pts))))

    if total_pts >= 80:
        level = "High"
    elif total_pts >= 60:
        level = "Medium-High"
    elif total_pts >= 40:
        level = "Moderate"
    else:
        level = "Developing"

    breakdown = {
        "affinity_pts": aff_pts,
        "spend_pts": spend_pts,
        "cat_pts": cat_pts,
        "rec_pts": rec_pts,
    }
    return total_pts, level, breakdown


def build_customer_evidence_and_reason(
    bucket,
    category,
    industry,
    spend,
    bought_exact,
    bought_switch,
    exact_qty,
    exact_val,
    exact_orders,
    switch_qty,
    switch_val,
    switch_orders,
    switch_skus,
    cat_qty,
    cat_val,
    cat_orders,
    other_cat_skus,
    prior_buyer_names,
    latest_active_month=None,
):
    """
    Constructs deterministic 'Relevant Purchase Evidence' and 'Reason' ('Why this customer?').
    """
    rec_str = f", last active {latest_active_month}" if latest_active_month else ""

    if bucket == 1:
        if bought_exact and bought_switch:
            sw_str = f" ({', '.join(switch_skus)})" if switch_skus else ""
            evidence = (
                f"Bought exact SKU ({int(exact_qty)} units, ₹{exact_val:,.0f}) & "
                f"SWITCH partner{sw_str} ({int(switch_qty)} units, ₹{switch_val:,.0f}){rec_str}"
            )
            reason = "Bucket 1 because the customer is eligible and previously purchased both this item and its switch partner."
        elif bought_exact:
            evidence = (
                f"Bought exact SKU: {int(exact_qty)} units (₹{exact_val:,.0f}) "
                f"across {exact_orders} order(s){rec_str}"
            )
            reason = "Bucket 1 because the customer is eligible and previously purchased this item."
        elif bought_switch:
            sw_str = f" ({', '.join(switch_skus)})" if switch_skus else ""
            evidence = (
                f"Bought SWITCH partner{sw_str}: {int(switch_qty)} units (₹{switch_val:,.0f}) "
                f"across {switch_orders} order(s){rec_str}"
            )
            reason = "Bucket 1 because the customer is eligible and previously purchased the switch partner item."
        else:
            evidence = f"Bought item or switch partner in 6M sales window{rec_str}"
            reason = "Bucket 1 because the customer is eligible and previously purchased this item or its switch partner."
    elif bucket == 2:
        prior_str = f" ({', '.join(prior_buyer_names[:2])})" if prior_buyer_names else ""
        ind_label = industry if pd.notna(industry) and str(industry).strip() else "Unassigned"
        ind_part = f"Industry '{ind_label}' matches previous buyers{prior_str}"
        if cat_val > 0:
            evidence = f"{ind_part}; customer 6M spend ₹{spend:,.0f} (incl. ₹{cat_val:,.0f} in {category}){rec_str}"
        else:
            evidence = f"{ind_part}; customer total 6M spend ₹{spend:,.0f}{rec_str}"
        reason = "Bucket 2 because the customer is eligible and operates in an industry associated with previous buyers of this item."
    else:
        other_sku_str = f" ({', '.join(other_cat_skus[:3])})" if other_cat_skus else ""
        evidence = (
            f"Bought {category} category: {int(cat_qty)} units (₹{cat_val:,.0f}) "
            f"across {cat_orders} order(s){other_sku_str}{rec_str}"
        )
        reason = f"Bucket 3 because the customer is eligible and previously purchased other items in the {category} category."

    return evidence, reason


def build_customer_targets(
    item_master, sales, analysis_items, validation=None, customers=None, config=None
):
    """
    R6 & R7 CUSTOMER TARGETING WITH OPPORTUNITY SCORING:

    Eligible customers:
      6-month purchase value > ₹100,000 (or config.customer_eligibility_spend).

    Bucket 1:
      Customers who previously bought the Push SKU or its switch partner.

    Bucket 2:
      Remaining eligible customers whose Industry matches an Industry
      associated with customers who previously bought the Push SKU.
      Customers with missing Industry cannot enter Bucket 2.

    Bucket 3:
      Remaining eligible customers who bought another item from the same Category.

    R7 Sorting:
      Bucket ascending, then 6-month purchase value descending.
      Deterministic tie-breaking on CustomerID.

    Rules enforced:
      - Only generate targets for Class == 'Push' (never Red List or No Action).
      - No duplication across buckets (mutually exclusive priority waterfall).
      - Opportunity Score does NOT move a customer between buckets or override R7 sort.
    """
    if config is None:
        config = get_default_config()

    # Resilient handling if 4th positional parameter was customers DataFrame
    if isinstance(validation, pd.DataFrame) and customers is None:
        customers = validation
        validation = None

    # 6-month purchase value per customer
    cust_sales = (
        sales.groupby(["CustomerID"], as_index=False)
        .agg(**{"6M Purchase Value": ("Value (Rs)", "sum")})
    )

    # Use Customers master as the source of truth for customer attributes
    if customers is not None:
        customer_info = customers.copy()
        customer_info["CustomerID"] = (
            customer_info["CustomerID"].astype(str).str.strip().str.upper()
        )
        customer_info["Industry"] = customer_info["Industry"].replace(
            ["nan", "None", ""], pd.NA
        )
        customer_info["Industry"] = customer_info["Industry"].apply(
            lambda x: x.strip() if isinstance(x, str) else x
        )
        customer_cols = [
            c
            for c in ["CustomerID", "CustomerName", "Industry", "Area"]
            if c in customer_info.columns
        ]
        customer_info = customer_info[customer_cols].drop_duplicates("CustomerID")
    else:
        customer_cols = ["CustomerID", "CustomerName", "Industry"]
        customer_info = sales[customer_cols].drop_duplicates("CustomerID")

    cust_name_map = customer_info.set_index("CustomerID")["CustomerName"].to_dict()

    customer_totals = customer_info.merge(
        cust_sales, on="CustomerID", how="left"
    )

    # Eligible customers: 6-month purchase value > threshold (default 100,000)
    eligible = customer_totals[
        customer_totals["6M Purchase Value"] > config.customer_eligibility_spend
    ].copy()

    eligible["Industry"] = eligible["Industry"].replace(["nan", "None", ""], np.nan)

    # Category map for all SKUs
    category_map = item_master.set_index("SKU")["Category"].to_dict()

    # Sales history at final analysis SKU (filter for valid purchases)
    sales_work = sales[(sales["Qty"] > 0) & (sales["Value (Rs)"] > 0)].copy()
    sales_work["Analysis_SKU"] = (
        sales_work["Analysis_SKU"].astype(str).str.strip().str.upper()
    )
    sales_work["CustomerID"] = (
        sales_work["CustomerID"].astype(str).str.strip().str.upper()
    )
    sales_work["Category"] = sales_work["Analysis_SKU"].map(category_map)

    # Pre-aggregate chronological months for recency calculation
    ordered_months, _ = (
        parse_and_sort_months(sales_work["Month"])
        if "Month" in sales_work.columns
        else ([], {})
    )
    month_rank = {m: i for i, m in enumerate(ordered_months)}
    n_months = len(ordered_months)

    # Customer latest transaction month
    cust_latest_months = {}
    if ordered_months and "Month" in sales_work.columns:
        for cid, m_series in sales_work.groupby("CustomerID")["Month"]:
            valid_m = [m for m in m_series if m in month_rank]
            if valid_m:
                cust_latest_months[cid] = max(valid_m, key=lambda m: month_rank[m])

    # Pre-aggregate Customer-SKU metrics
    cust_sku_grouped = {}
    for (cid, a_sku), grp in sales_work.groupby(["CustomerID", "Analysis_SKU"]):
        exact_mask = grp["SKU"] == a_sku
        switch_mask = ~exact_mask
        exact_qty = grp.loc[exact_mask, "Qty"].sum()
        exact_val = grp.loc[exact_mask, "Value (Rs)"].sum()
        exact_orders = exact_mask.sum()
        switch_qty = grp.loc[switch_mask, "Qty"].sum()
        switch_val = grp.loc[switch_mask, "Value (Rs)"].sum()
        switch_orders = switch_mask.sum()
        switch_skus = grp.loc[switch_mask, "SKU"].unique().tolist()
        cust_sku_grouped[(cid, a_sku)] = {
            "bought_exact": exact_orders > 0,
            "exact_qty": exact_qty,
            "exact_val": exact_val,
            "exact_orders": exact_orders,
            "bought_switch": switch_orders > 0,
            "switch_qty": switch_qty,
            "switch_val": switch_val,
            "switch_orders": switch_orders,
            "switch_skus": switch_skus,
        }

    # Pre-aggregate Customer-Category metrics
    cust_cat_grouped = {}
    for (cid, cat), grp in sales_work.groupby(["CustomerID", "Category"]):
        cat_qty = grp["Qty"].sum()
        cat_val = grp["Value (Rs)"].sum()
        cat_orders = len(grp)
        other_skus = grp["Analysis_SKU"].unique().tolist()
        cust_cat_grouped[(cid, cat)] = {
            "cat_qty": cat_qty,
            "cat_val": cat_val,
            "cat_orders": cat_orders,
            "other_skus": other_skus,
        }

    # For each customer, which analysis SKUs were bought?
    customer_sku = (
        sales_work.groupby(["CustomerID", "Analysis_SKU"])
        .agg({"Qty": "sum"})
        .reset_index()
    )
    customer_sku["Category"] = customer_sku["Analysis_SKU"].map(category_map)

    # Industry set for each Push item based on customers who bought that item or its switch partner
    item_industries = (
        sales_work.merge(
            customer_info[["CustomerID", "Industry"]],
            on="CustomerID",
            how="left",
            suffixes=("", "_master"),
        )
        .groupby("Analysis_SKU")["Industry_master"]
        .apply(lambda s: set(x for x in s.dropna() if str(x).strip() != ""))
        .to_dict()
    )

    # Precompute SKU buyers and Customer categories for O(1) membership lookups
    sku_buyers = customer_sku.groupby("Analysis_SKU")["CustomerID"].apply(set).to_dict()
    cust_categories = customer_sku.groupby("CustomerID")["Category"].apply(lambda s: set(s.dropna())).to_dict()
    eligible_records = eligible.to_dict("records")

    targets = {}

    # Target ONLY Push items (never Red List or No Action items)
    push_items = analysis_items[analysis_items["Class"] == "Push"]

    for _, item in push_items.iterrows():
        sku = item["SKU"]
        category = item["Category"]

        # Bucket 1 candidates: bought this item or its switch partner
        bought_before = sku_buyers.get(sku, set())

        item_industry_set = item_industries.get(sku, set())

        # Prior buyer names for evidence
        prior_buyer_names = [
            cust_name_map.get(cid, cid)
            for cid in customer_info["CustomerID"]
            if cid in bought_before
        ]

        rows = []
        for customer in eligible_records:
            cid = customer["CustomerID"]

            # Mutual exclusivity: once assigned to a bucket, customer cannot enter subsequent buckets
            if cid in bought_before:
                bucket = 1
                bucket_name = "1 - Bought Before"
            elif (
                pd.notna(customer["Industry"])
                and customer["Industry"] in item_industry_set
            ):
                bucket = 2
                bucket_name = "2 - Similar Business"
            else:
                bought_categories = cust_categories.get(cid, set())
                if category in bought_categories:
                    bucket = 3
                    bucket_name = "3 - Same Category"
                else:
                    continue

            # Customer SKU metrics
            sku_info = cust_sku_grouped.get(
                (cid, sku),
                {
                    "bought_exact": False,
                    "exact_qty": 0,
                    "exact_val": 0.0,
                    "exact_orders": 0,
                    "bought_switch": False,
                    "switch_qty": 0,
                    "switch_val": 0.0,
                    "switch_orders": 0,
                    "switch_skus": [],
                },
            )

            # Customer Category metrics
            cat_info = cust_cat_grouped.get(
                (cid, category),
                {
                    "cat_qty": 0,
                    "cat_val": 0.0,
                    "cat_orders": 0,
                    "other_skus": [],
                },
            )

            # Recency gap
            cust_latest_m = cust_latest_months.get(cid)
            if cust_latest_m and cust_latest_m in month_rank and n_months > 0:
                rec_gap = (n_months - 1) - month_rank[cust_latest_m]
            else:
                rec_gap = None

            # Opportunity score (0-100)
            opp_score, opp_level, _ = calculate_customer_opportunity_score(
                spend=customer["6M Purchase Value"],
                bucket=bucket,
                bought_exact=sku_info["bought_exact"],
                bought_switch=sku_info["bought_switch"],
                category_spend=cat_info["cat_val"],
                recency_gap=rec_gap,
            )

            # Deterministic evidence and reason
            evidence, reason = build_customer_evidence_and_reason(
                bucket=bucket,
                category=category,
                industry=customer["Industry"],
                spend=customer["6M Purchase Value"],
                bought_exact=sku_info["bought_exact"],
                bought_switch=sku_info["bought_switch"],
                exact_qty=sku_info["exact_qty"],
                exact_val=sku_info["exact_val"],
                exact_orders=sku_info["exact_orders"],
                switch_qty=sku_info["switch_qty"],
                switch_val=sku_info["switch_val"],
                switch_orders=sku_info["switch_orders"],
                switch_skus=sku_info["switch_skus"],
                cat_qty=cat_info["cat_qty"],
                cat_val=cat_info["cat_val"],
                cat_orders=cat_info["cat_orders"],
                other_cat_skus=[s for s in cat_info["other_skus"] if s != sku],
                prior_buyer_names=prior_buyer_names,
                latest_active_month=cust_latest_m,
            )

            rows.append({
                "CustomerID": cid,
                "Customer ID": cid,
                "CustomerName": customer["CustomerName"],
                "Industry": customer["Industry"],
                "6M Purchase Value": customer["6M Purchase Value"],
                "Bucket": bucket,
                "Bucket Name": bucket_name,
                "Relevant Purchase Evidence": evidence,
                "Opportunity Score": opp_score,
                "Opportunity Level": opp_level,
                "Reason": reason,
                "Why this customer?": reason,
            })

        result = pd.DataFrame(rows)

        if result.empty:
            targets[sku] = result
            continue

        # Area mapping
        area_map = {}
        if customers is not None and "Area" in customer_info.columns:
            area_map = (
                customer_info.drop_duplicates("CustomerID")
                .set_index("CustomerID")["Area"]
                .to_dict()
            )
        result["Area"] = result["CustomerID"].map(area_map)

        # R7: Sort by Bucket ascending, then 6-month purchase value descending
        # CustomerID serves as tie-breaker for deterministic reproducibility
        result = result.sort_values(
            ["Bucket", "6M Purchase Value", "CustomerID"],
            ascending=[True, False, True],
        ).reset_index(drop=True)
        result.insert(0, "Priority", range(1, len(result) + 1))

        targets[sku] = result

    total_opps = sum(len(df) for df in targets.values())
    logger.info(
        "build_customer_targets complete: %d Push SKUs mapped to %d total customer opportunities",
        len(targets), total_opps
    )
    return targets
