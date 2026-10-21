import re
from typing import Dict, List, Any, Tuple
import numpy as np
import pandas as pd
from src.logger import get_logger

logger = get_logger("Validation")

EXPECTED_COLUMNS = {
    "Item_Master": [
        "SKU", "Item Name", "Category", "Master Pack Qty",
        "Unit Cost (Rs)", "Alternate Item (name)", "Alternate Flag", "Status"
    ],
    "Stock_Aging": [
        "SKU", "Qty 0-30 days", "Qty 31-60 days", "Qty 61-90 days",
        "Qty 91-180 days", "Qty 180+ days"
    ],
    "Sales_Lines": [
        "Month", "CustomerID", "CustomerName", "Industry",
        "SKU", "Qty", "Value (Rs)"
    ],
    "Customers": ["CustomerID", "CustomerName", "Industry", "Area"],
}

IMPORTANT_FIELDS = {
    "Item_Master": ["SKU", "Item Name", "Category", "Master Pack Qty", "Unit Cost (Rs)", "Status"],
    "Stock_Aging": ["SKU"],
    "Sales_Lines": ["Month", "CustomerID", "CustomerName", "SKU", "Qty", "Value (Rs)"],
    "Customers": ["CustomerID", "CustomerName", "Area"],
}

RECOGNIZED_FLAGS = {"SWITCH", "EXCLUDE"}
RECOGNIZED_STATUSES = {"ACTIVE", "INACTIVE"}


def _clean_name(val):
    """Normalize whitespace and uppercase an item name for reliable matching."""
    if pd.isna(val):
        return ""
    text = str(val).strip()
    return re.sub(r"\s+", " ", text).upper()


def _issue(
    severity: str,
    issue_type: str,
    sheet: str,
    column: str,
    count: int,
    description: str,
    tool_handling: str,
    recommended_source_fix: str
) -> dict:
    """
    Creates a standardized, structured validation issue record.
    Preserves full backward compatibility with existing tests and UI components.
    """
    return {
        # Core structured validation fields
        "Severity": severity.upper(),  # ERROR, WARNING, INFO
        "Issue Type": issue_type,
        "Sheet": sheet,
        "Column": column,
        "Number of affected rows": int(count),
        "Description": description,
        "How the application handled the issue": tool_handling,
        # Backward-compatibility aliases
        "Problem": description,
        "Count": int(count),
        "Number of affected records": int(count),
        "What the tool did": tool_handling,
        "Tool Handling": tool_handling,
        "Recommended Source Fix": recommended_source_fix,
        "Recommended source-level fix": recommended_source_fix,
    }


def calculate_data_quality_score(issues: list, frames: dict) -> int:
    """
    Computes an objective, deterministic Data Quality Score from 0 to 100.

    Formula:
    - Base: 100 points
    - ERROR: -35 points per error (severe integrity violation halting analysis)
    - WARNING: -3.0 to -10.0 points per warning, scaled by proportion of affected rows
    - INFO: -0.5 to -3.0 points per info item (normal cleaning/disclosures)

    Bounded strictly between 0 and 100.
    """
    if not issues:
        return 100

    deductions = 0.0
    for iss in issues:
        sev = iss.get("Severity", "WARNING").upper()
        count = iss.get("Number of affected rows", iss.get("Count", 0))
        sheet = iss.get("Sheet", "")

        total_rows = (
            len(frames.get(sheet, []))
            if sheet in frames and isinstance(frames[sheet], pd.DataFrame)
            else 100
        )
        ratio = count / max(1, total_rows)

        if sev == "ERROR":
            deductions += 35.0
        elif sev == "WARNING":
            deductions += min(10.0, 3.0 + 7.0 * ratio)
        elif sev == "INFO":
            deductions += min(3.0, 0.5 + 2.5 * ratio)
        else:
            deductions += 2.0

    return max(0, min(100, int(round(100.0 - deductions))))


def validate_data(item_master, stock_aging, sales_lines, customers, raise_on_error=True):
    """
    Validates the four core tables across all 18 dimensions:
      1. Missing required sheets
      2. Missing required columns
      3. Blank SKU
      4. Duplicate SKU in Item_Master
      5. Invalid numeric values
      6. Negative stock
      7. Negative sales quantity
      8. Negative unit cost
      9. Invalid dates
      10. Missing Customer ID
      11. Missing Industry
      12. Missing Category
      13. Missing Master Pack
      14. Invalid Master Pack values
      15. Duplicate Sales_Lines records
      16. Invalid Alternate Flag
      17. SWITCH records with missing new/partner SKU information
      18. Customers with missing purchase information

    Classifies every issue by Severity:
      - ERROR: Prevents analysis when data cannot be reliably processed.
      - WARNING: Allows processing with clear disclosure and safe fallback.
      - INFO: Documents normal cleaning, formatting, or operational transformations.

    Computes a Data Quality Score (0-100).
    Preserves original uploaded data in 'raw_data' and cleaned copies in 'cleaned_data'.
    """
    issues = []

    frames = {
        "Item_Master": item_master,
        "Stock_Aging": stock_aging,
        "Sales_Lines": sales_lines,
        "Customers": customers,
    }

    # 1. MISSING REQUIRED SHEETS
    for name, df in frames.items():
        if df is None or not isinstance(df, pd.DataFrame):
            err_msg = f"Table {name} is missing or not a valid DataFrame."
            issues.append(_issue(
                severity="ERROR",
                issue_type="Missing Sheet",
                sheet=name,
                column="N/A",
                count=0,
                description=err_msg,
                tool_handling="Halted analysis. All four core worksheets must be provided for processing.",
                recommended_source_fix=f"Provide a valid {name} worksheet in the export."
            ))
            if raise_on_error:
                raise ValueError(err_msg)

    # 2. MISSING REQUIRED COLUMNS
    for name, expected in EXPECTED_COLUMNS.items():
        df = frames[name]
        missing = [c for c in expected if c not in df.columns]
        if missing:
            if len(missing) == 1:
                col_name = missing[0]
                desc = (
                    f"{name} is missing columns: {missing}. "
                    f"'{col_name}' is missing from {name}. "
                    f"Please upload the latest system export containing the required {col_name} column."
                )
            else:
                cols_str = ", ".join(f"'{c}'" for c in missing)
                desc = (
                    f"{name} is missing columns: {missing}. "
                    f"Required column(s) {cols_str} are missing from {name}. "
                    f"Please upload the latest system export containing the required columns."
                )

            issues.append(_issue(
                severity="ERROR",
                issue_type="Missing Column",
                sheet=name,
                column=", ".join(missing),
                count=0,
                description=desc,
                tool_handling="Halted analysis. Required schema columns must be present for downstream business logic.",
                recommended_source_fix=f"Ensure system export query extracts all standard columns for {name}."
            ))
            if raise_on_error:
                raise ValueError(desc)

    # 3. EMPTY FILES / SHEETS
    for name, df in frames.items():
        if df.empty:
            issues.append(_issue(
                severity="ERROR",
                issue_type="Empty Sheet",
                sheet=name,
                column="All Columns",
                count=0,
                description=f"{name} is empty",
                tool_handling="Stop processing and ask for a valid export.",
                recommended_source_fix="Ensure the monthly export contains records."
            ))

    # 4. BLANK SKU
    for name in ["Item_Master", "Stock_Aging", "Sales_Lines"]:
        df = frames[name]
        if "SKU" in df.columns:
            is_null = df["SKU"].isna()
            is_blank = df["SKU"].astype(str).str.strip().isin(["", "nan", "None", "NA", "<NA>"])
            blank_sku_count = int((is_null | is_blank).sum())
            if blank_sku_count > 0:
                sev = "ERROR" if (name == "Item_Master" and blank_sku_count == len(df)) else "WARNING"
                issues.append(_issue(
                    severity=sev,
                    issue_type="Blank SKU",
                    sheet=name,
                    column="SKU",
                    count=blank_sku_count,
                    description=f"Missing values in {name} (SKU)",
                    tool_handling=f"Flag records with missing SKU and exclude from item-level analysis.",
                    recommended_source_fix=f"Ensure every product record in {name} has a valid, non-empty SKU."
                ))

    # 5. DUPLICATE SKU IN ITEM_MASTER
    if "SKU" in item_master.columns:
        im_skus = item_master["SKU"].dropna().astype(str).str.strip().str.upper()
        im_skus = im_skus[~im_skus.isin(["", "NAN", "NONE", "NA", "<NA>"])]
        dup_sku_count = int(im_skus.duplicated().sum())
        if dup_sku_count > 0:
            issues.append(_issue(
                severity="WARNING",
                issue_type="Duplicate SKU",
                sheet="Item_Master",
                column="SKU",
                count=dup_sku_count,
                description="Duplicate SKU definitions in Item_Master",
                tool_handling="Deduplicated catalog items by retaining the first occurrence to prevent duplicate join artifacts.",
                recommended_source_fix="Enforce a unique primary key constraint on SKU in the product master database."
            ))

    # 6. MISSING CATEGORY
    if "Category" in item_master.columns:
        cat_null = item_master["Category"].isna() | item_master["Category"].astype(str).str.strip().isin(["", "nan", "None", "NA", "<NA>"])
        missing_cat = int(cat_null.sum())
        if missing_cat > 0:
            issues.append(_issue(
                severity="WARNING",
                issue_type="Missing Category",
                sheet="Item_Master",
                column="Category",
                count=missing_cat,
                description="Missing values in Item_Master (Category)",
                tool_handling="Flag missing Category; affected items cannot participate in Bucket 3 (Same Category) customer affinity targeting.",
                recommended_source_fix="Assign product category taxonomy to all items in Item_Master."
            ))

    # 7. MISSING MASTER PACK
    if "Master Pack Qty" in item_master.columns:
        mp_null = item_master["Master Pack Qty"].isna() | item_master["Master Pack Qty"].astype(str).str.strip().isin(["", "nan", "None", "NA", "<NA>"])
        missing_mp = int(mp_null.sum())
        if missing_mp > 0:
            issues.append(_issue(
                severity="WARNING",
                issue_type="Missing Master Pack",
                sheet="Item_Master",
                column="Master Pack Qty",
                count=missing_mp,
                description="Missing values in Item_Master (Master Pack Qty)",
                tool_handling="Flag missing Master Pack Qty; required for Red List classification threshold (Rule R5).",
                recommended_source_fix="Ensure Master Pack Qty is populated for every catalog item in Item_Master."
            ))

    # 8. INVALID MASTER PACK VALUES & UNIT COST IN ITEM_MASTER
    if "Master Pack Qty" in item_master.columns:
        s_mp = pd.to_numeric(item_master["Master Pack Qty"], errors="coerce")
        invalid_mp = int((s_mp.isna() | (s_mp <= 0)).sum())
        if invalid_mp > 0:
            issues.append(_issue(
                severity="WARNING",
                issue_type="Invalid Master Pack Values",
                sheet="Item_Master",
                column="Master Pack Qty",
                count=invalid_mp,
                description="Invalid numeric values in Item_Master (Master Pack Qty)",
                tool_handling="Flag records with non-positive or non-numeric Master Pack Qty.",
                recommended_source_fix="Ensure Master Pack Qty contains valid positive numbers in Item_Master."
            ))

    if "Unit Cost (Rs)" in item_master.columns:
        s_cost = pd.to_numeric(item_master["Unit Cost (Rs)"], errors="coerce")
        invalid_cost = int((s_cost.isna() | (s_cost <= 0)).sum())
        if invalid_cost > 0:
            is_neg = (s_cost < 0).any()
            issues.append(_issue(
                severity="WARNING",
                issue_type="Negative Unit Cost" if is_neg else "Invalid Numeric Values",
                sheet="Item_Master",
                column="Unit Cost (Rs)",
                count=invalid_cost,
                description="Invalid numeric values in Item_Master (Unit Cost (Rs))",
                tool_handling="Flag records with non-positive or non-numeric Unit Cost (Rs).",
                recommended_source_fix="Ensure Unit Cost (Rs) contains valid positive numbers in Item_Master."
            ))

    # 9. GENERAL MISSING VALUES IN IMPORTANT FIELDS (e.g. Item Name, Month, CustomerID)
    for name, fields in IMPORTANT_FIELDS.items():
        df = frames[name]
        for field in fields:
            # Skip fields already covered by specialized checks
            if (name == "Item_Master" and field in ["SKU", "Category", "Master Pack Qty", "Unit Cost (Rs)"]) or \
               (name in ["Stock_Aging", "Sales_Lines"] and field == "SKU"):
                continue

            if field in df.columns:
                is_null = df[field].isna()
                if df[field].dtype == object or pd.api.types.is_string_dtype(df[field]):
                    is_empty_str = df[field].astype(str).str.strip().isin(["", "nan", "None", "NA", "<NA>"])
                    missing_count = int((is_null | is_empty_str).sum())
                else:
                    missing_count = int(is_null.sum())

                if missing_count > 0:
                    if field == "CustomerID":
                        handling = "Flag records with missing CustomerID; exclude from customer-level targeting."
                        fix = f"Ensure every customer record in {name} has a valid CustomerID."
                        issue_type = "Missing Customer ID"
                    else:
                        handling = f"Flag missing {field} and handle or exclude appropriately during processing."
                        fix = f"Ensure {field} is fully populated in {name} source exports."
                        issue_type = f"Missing {field}"

                    issues.append(_issue(
                        severity="WARNING",
                        issue_type=issue_type,
                        sheet=name,
                        column=field,
                        count=missing_count,
                        description=f"Missing values in {name} ({field})",
                        tool_handling=handling,
                        recommended_source_fix=fix
                    ))

    # 10. STOCK_AGING: INVALID NUMERIC & NEGATIVE STOCK
    stock_cols = [
        "Qty 0-30 days", "Qty 31-60 days", "Qty 61-90 days",
        "Qty 91-180 days", "Qty 180+ days"
    ]
    for c in stock_cols:
        if c in stock_aging.columns:
            s = pd.to_numeric(stock_aging[c], errors="coerce")
            invalid_count = int((s.isna() | (s < 0)).sum())
            if invalid_count > 0:
                is_neg = (s < 0).any()
                issues.append(_issue(
                    severity="WARNING",
                    issue_type="Negative Stock Quantity" if is_neg else "Invalid Numeric Values",
                    sheet="Stock_Aging",
                    column=c,
                    count=invalid_count,
                    description=f"Invalid numeric values in Stock_Aging ({c})",
                    tool_handling="Replace invalid/negative aging quantities with 0 during aggregation.",
                    recommended_source_fix=f"Ensure {c} contains valid non-negative quantities."
                ))

    # 11. SALES_LINES: INVALID NUMERIC & NEGATIVE SALES QUANTITY
    for col in ["Qty", "Value (Rs)"]:
        if col in sales_lines.columns:
            s = pd.to_numeric(sales_lines[col], errors="coerce")
            invalid_count = int((s.isna() | (s <= 0)).sum())
            if invalid_count > 0:
                is_neg = (col == "Qty" and (s < 0).any())
                issues.append(_issue(
                    severity="WARNING",
                    issue_type="Negative Sales Quantity" if is_neg else "Invalid Numeric Values",
                    sheet="Sales_Lines",
                    column=col,
                    count=invalid_count,
                    description=f"Invalid numeric values in Sales_Lines ({col})",
                    tool_handling=f"Flag sales transactions with non-positive {col}.",
                    recommended_source_fix=f"Ensure {col} contains valid positive numbers in Sales_Lines."
                ))

    # 12. SALES_LINES: INVALID DATES IN MONTH
    if "Month" in sales_lines.columns:
        raw_months = sales_lines["Month"].dropna().astype(str).str.strip()
        meaningful_months = raw_months[~raw_months.isin(["", "nan", "None", "NA", "<NA>"])]
        if not meaningful_months.empty:
            parsed_dates = pd.to_datetime(meaningful_months, format="mixed", errors="coerce")
            invalid_date_count = int(parsed_dates.isna().sum())
            if invalid_date_count > 0:
                issues.append(_issue(
                    severity="WARNING",
                    issue_type="Invalid Date Values",
                    sheet="Sales_Lines",
                    column="Month",
                    count=invalid_date_count,
                    description="Invalid or unparseable dates in Sales_Lines (Month)",
                    tool_handling="Coerced unparseable dates to standard period string; included in 6-month aggregate based on file window.",
                    recommended_source_fix="Standardize export date formatting to 'Mon-YYYY' or 'YYYY-MM-DD'."
                ))

    # 13. EXACT DUPLICATE SALES ROWS
    dup_count = int(sales_lines.duplicated().sum())
    if dup_count:
        issues.append(_issue(
            severity="INFO",
            issue_type="Duplicate Sales Records",
            sheet="Sales_Lines",
            column="All Columns",
            count=dup_count,
            description="Exact duplicate sales rows",
            tool_handling="Remove exact duplicates before aggregation.",
            recommended_source_fix="Provide a unique transaction/line ID at source."
        ))

    # 14. SKU FORMATTING INCONSISTENCIES
    for name, df in [("Item_Master", item_master), ("Stock_Aging", stock_aging), ("Sales_Lines", sales_lines)]:
        if "SKU" in df.columns:
            raw = df["SKU"].astype(str)
            normalized = raw.str.strip().str.upper()
            changed = int((raw != normalized).sum())
            if changed:
                issues.append(_issue(
                    severity="INFO",
                    issue_type="Formatting",
                    sheet=name,
                    column="SKU",
                    count=changed,
                    description=f"SKU formatting inconsistencies in {name}",
                    tool_handling="Trim whitespace and convert SKU to uppercase.",
                    recommended_source_fix="Enforce a standardized SKU format in system exports."
                ))

    # 15. CUSTOMERID FORMATTING INCONSISTENCIES
    for name, df in [("Sales_Lines", sales_lines), ("Customers", customers)]:
        if "CustomerID" in df.columns:
            raw = df["CustomerID"].astype(str)
            normalized = raw.str.strip().str.upper()
            changed = int((raw != normalized).sum())
            if changed:
                issues.append(_issue(
                    severity="INFO",
                    issue_type="Formatting",
                    sheet=name,
                    column="CustomerID",
                    count=changed,
                    description=f"CustomerID formatting inconsistencies in {name}",
                    tool_handling="Trim whitespace and convert CustomerID to uppercase.",
                    recommended_source_fix="Enforce a standardized CustomerID format in system exports."
                ))

    # 16. REFERENTIAL INTEGRITY: SALES SKUS NOT IN ITEM_MASTER
    item_skus = set(item_master["SKU"].dropna().astype(str).str.strip().str.upper()) - {"", "NAN", "NONE", "NA", "<NA>"}
    sales_skus = set(sales_lines["SKU"].dropna().astype(str).str.strip().str.upper()) - {"", "NAN", "NONE", "NA", "<NA>"}
    orphan_skus = len(sales_skus - item_skus)
    if orphan_skus:
        issues.append(_issue(
            severity="WARNING",
            issue_type="Referential Integrity",
            sheet="Sales_Lines",
            column="SKU",
            count=orphan_skus,
            description="Sales SKUs not found in item master",
            tool_handling="Flag unmatched SKUs and exclude them from item-level classification.",
            recommended_source_fix="Ensure all transactional SKUs exist in the item master."
        ))

    # 17. REFERENTIAL INTEGRITY: SALES CUSTOMERIDS NOT IN CUSTOMERS
    customer_ids = set(customers["CustomerID"].dropna().astype(str).str.strip().str.upper()) - {"", "NAN", "NONE", "NA", "<NA>"}
    sales_customer_ids = set(sales_lines["CustomerID"].dropna().astype(str).str.strip().str.upper()) - {"", "NAN", "NONE", "NA", "<NA>"}
    orphan_customers = len(sales_customer_ids - customer_ids)
    if orphan_customers:
        issues.append(_issue(
            severity="WARNING",
            issue_type="Referential Integrity",
            sheet="Sales_Lines",
            column="CustomerID",
            count=orphan_customers,
            description="Sales customer IDs not found in customer master",
            tool_handling="Retain sales rows but flag the unmatched customers.",
            recommended_source_fix="Maintain referential integrity between sales and customer master."
        ))

    # 18. CUSTOMERS WITH MISSING INDUSTRY
    if "Industry" in customers.columns:
        ind_str = customers["Industry"].astype(str).str.strip()
        missing_industry = int(
            (customers["Industry"].isna() | ind_str.isin(["", "nan", "None", "NA", "<NA>"])).sum()
        )
        if missing_industry:
            issues.append(_issue(
                severity="WARNING",
                issue_type="Missing Industry",
                sheet="Customers",
                column="Industry",
                count=missing_industry,
                description="Customers with missing industry",
                tool_handling="Do not allow these customers into Bucket 2.",
                recommended_source_fix="Make customer industry mandatory."
            ))

    # 19. INVALID ALTERNATE FLAG
    if "Alternate Flag" in item_master.columns:
        flags = item_master["Alternate Flag"].dropna().astype(str).str.strip().str.upper()
        meaningful_flags = flags[~flags.isin(["", "NAN", "NONE", "NA", "<NA>"])]
        unrecognised_flags = int((~meaningful_flags.isin(RECOGNIZED_FLAGS)).sum())
        if unrecognised_flags:
            issues.append(_issue(
                severity="WARNING",
                issue_type="Invalid Alternate Flag",
                sheet="Item_Master",
                column="Alternate Flag",
                count=unrecognised_flags,
                description="Invalid or unrecognised Alternate Flag values in Item_Master",
                tool_handling="Ignore unrecognised flag values and treat as standard items.",
                recommended_source_fix="Use only recognized Alternate Flag values (e.g. SWITCH, EXCLUDE) in Item_Master."
            ))

    # 20. UNRESOLVED SWITCH MAPPINGS (SWITCH flag without valid partner SKU/name)
    if "Alternate Flag" in item_master.columns and "Alternate Item (name)" in item_master.columns and "Item Name" in item_master.columns:
        switch_rows = item_master[
            item_master["Alternate Flag"].astype(str).str.strip().str.upper() == "SWITCH"
        ].copy()
        if not switch_rows.empty:
            alt_names = switch_rows["Alternate Item (name)"].astype(str).str.strip()
            missing_partner = alt_names.isin(["", "nan", "None", "NA", "<NA>"])
            known_names = set(item_master["Item Name"].dropna().apply(_clean_name))
            cleaned_alts = alt_names.apply(_clean_name)
            unmatched_partner = ~missing_partner & (~cleaned_alts.isin(known_names))
            unresolved_count = int((missing_partner | unmatched_partner).sum())
            if unresolved_count > 0:
                issues.append(_issue(
                    severity="WARNING",
                    issue_type="Unresolved Switch Mapping",
                    sheet="Item_Master",
                    column="Alternate Item (name)",
                    count=unresolved_count,
                    description="SWITCH records with missing or unresolvable partner item in Item_Master",
                    tool_handling="Flagged unresolved switch; retained original SKU as an independent analytical item to prevent data loss.",
                    recommended_source_fix="Ensure Alternate Item (name) exactly matches the Item Name of the replacement pack size in Item_Master."
                ))

    # 21. INVALID STATUS VALUES
    if "Status" in item_master.columns:
        statuses = item_master["Status"].dropna().astype(str).str.strip().str.upper()
        invalid_status = int(
            (item_master["Status"].isna() | (~statuses.isin(RECOGNIZED_STATUSES))).sum()
        )
        if invalid_status:
            issues.append(_issue(
                severity="WARNING",
                issue_type="Invalid Status",
                sheet="Item_Master",
                column="Status",
                count=invalid_status,
                description="Invalid or missing Status values in Item_Master",
                tool_handling="Exclude records with invalid status from active analysis.",
                recommended_source_fix="Set Status to Active or Inactive for all Item_Master records."
            ))

    # 22. CUSTOMERS WITH MISSING PURCHASE INFORMATION (Zero Recorded Purchases)
    if "CustomerID" in customers.columns and "CustomerID" in sales_lines.columns:
        valid_cust_ids = set(customers["CustomerID"].dropna().astype(str).str.strip().str.upper()) - {"", "NAN", "NONE", "NA", "<NA>"}
        valid_sales_cust_ids = set(sales_lines["CustomerID"].dropna().astype(str).str.strip().str.upper()) - {"", "NAN", "NONE", "NA", "<NA>"}
        no_purchase_cust = len(valid_cust_ids - valid_sales_cust_ids)
        if no_purchase_cust > 0:
            issues.append(_issue(
                severity="INFO",
                issue_type="Customer Without Purchases",
                sheet="Customers",
                column="CustomerID",
                count=no_purchase_cust,
                description="Customer master accounts with zero recorded purchases",
                tool_handling="Recorded 6-month purchase value as ₹0. Ineligible for outbound Push campaigns under Rule R6 (> ₹100,000 threshold).",
                recommended_source_fix="Normal for newly onboarded or dormant accounts; verify if missing sales lines occurred."
            ))

    # Calculate Data Quality Score (0-100)
    score = calculate_data_quality_score(issues, frames)
    has_errors = any(i.get("Severity") == "ERROR" for i in issues)

    # Build clean copies for separate preservation without mutating inputs
    clean_im = item_master.copy()
    if "SKU" in clean_im.columns:
        clean_im["SKU"] = clean_im["SKU"].astype(str).str.strip().str.upper()
        # Retain first valid definition if duplicates exist
        clean_im = clean_im.drop_duplicates(subset=["SKU"], keep="first").copy()
    if "Status" in clean_im.columns:
        clean_im["Status"] = clean_im["Status"].astype(str).str.strip().str.title()

    clean_stock = stock_aging.copy()
    if "SKU" in clean_stock.columns:
        clean_stock["SKU"] = clean_stock["SKU"].astype(str).str.strip().str.upper()
    for c in stock_cols:
        if c in clean_stock.columns:
            clean_stock[c] = pd.to_numeric(clean_stock[c], errors="coerce").fillna(0).clip(lower=0)

    clean_sales = sales_lines.copy()
    if "SKU" in clean_sales.columns:
        clean_sales["SKU"] = clean_sales["SKU"].astype(str).str.strip().str.upper()
    if "CustomerID" in clean_sales.columns:
        clean_sales["CustomerID"] = clean_sales["CustomerID"].astype(str).str.strip().str.upper()
    clean_sales = clean_sales.drop_duplicates().copy()

    clean_cust = customers.copy()
    if "CustomerID" in clean_cust.columns:
        clean_cust["CustomerID"] = clean_cust["CustomerID"].astype(str).str.strip().str.upper()

    n_errors = sum(1 for i in issues if i.get("Severity") == "ERROR")
    n_warnings = sum(1 for i in issues if i.get("Severity") == "WARNING")
    n_info = sum(1 for i in issues if i.get("Severity") == "INFO")

    logger.info(
        "Validation complete: Data Quality Score=%d/100, Issues=%d (Errors=%d, Warnings=%d, Info=%d)",
        score, len(issues), n_errors, n_warnings, n_info
    )

    return {
        "issues": issues,
        "data_quality_score": score,
        "has_errors": has_errors,
        "duplicate_sales_rows": dup_count,
        "summary": {
            "total_issues": len(issues),
            "errors": n_errors,
            "warnings": n_warnings,
            "info": n_info,
            "data_quality_score": score,
        },
        "raw_data": {
            "Item_Master": item_master.copy(),
            "Stock_Aging": stock_aging.copy(),
            "Sales_Lines": sales_lines.copy(),
            "Customers": customers.copy(),
        },
        "cleaned_data": {
            "Item_Master": clean_im,
            "Stock_Aging": clean_stock,
            "Sales_Lines": clean_sales,
            "Customers": clean_cust,
        },
    }
