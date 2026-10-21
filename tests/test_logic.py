import numpy as np
import pandas as pd
import pytest

from src.business_logic import run_analysis, build_switch_map
from src.customer_targets import build_customer_targets

PATH = "sample_data/CompanyX_Data.xlsx"


def test_required_classifications():
    item_master = pd.read_excel(PATH, sheet_name="Item_Master")
    stock = pd.read_excel(PATH, sheet_name="Stock_Aging")
    sales = pd.read_excel(PATH, sheet_name="Sales_Lines")
    customers = pd.read_excel(PATH, sheet_name="Customers")

    result = run_analysis(item_master, stock, sales, customers)
    items = result["analysis_items"].set_index("SKU")

    assert items.loc["SKU1001", "Class"] == "No Action"
    assert items.loc["SKU1006", "Class"] == "Push"
    assert items.loc["SKU1019", "Class"] == "Push"
    assert items.loc["SKU1005", "Class"] == "Push"


def test_class_counts():
    item_master = pd.read_excel(PATH, sheet_name="Item_Master")
    stock = pd.read_excel(PATH, sheet_name="Stock_Aging")
    sales = pd.read_excel(PATH, sheet_name="Sales_Lines")
    customers = pd.read_excel(PATH, sheet_name="Customers")

    result = run_analysis(item_master, stock, sales, customers)
    items = result["analysis_items"]

    counts = items["Class"].value_counts().to_dict()

    assert counts.get("Red List", 0) == 7
    assert counts.get("No Action", 0) == 13
    assert counts.get("Push", 0) == 18


def test_push_aged_value_benchmark():
    item_master = pd.read_excel(PATH, sheet_name="Item_Master")
    stock = pd.read_excel(PATH, sheet_name="Stock_Aging")
    sales = pd.read_excel(PATH, sheet_name="Sales_Lines")
    customers = pd.read_excel(PATH, sheet_name="Customers")

    result = run_analysis(item_master, stock, sales, customers)
    items = result["analysis_items"]

    push_val = float(items.loc[items["Class"] == "Push", "Aged Value"].sum())
    assert push_val == 163841.0


def test_customer_targets_sku1005_top_order():
    item_master = pd.read_excel(PATH, sheet_name="Item_Master")
    stock = pd.read_excel(PATH, sheet_name="Stock_Aging")
    sales = pd.read_excel(PATH, sheet_name="Sales_Lines")
    customers = pd.read_excel(PATH, sheet_name="Customers")

    result = run_analysis(item_master, stock, sales, customers)
    targets = build_customer_targets(
        result["clean_item_master"],
        result["clean_sales"],
        result["analysis_items"],
        customers=customers
    )

    t = targets["SKU1005"]
    assert not t.empty
    # Customer 220 must be first (Bucket 1)
    assert t.iloc[0]["CustomerID"] == "C220"
    assert t.iloc[0]["Bucket"] == 1
    # Customer 224 must be second (Bucket 1)
    assert t.iloc[1]["CustomerID"] == "C224"
    assert t.iloc[1]["Bucket"] == 1
    # Customer 214 must be third (Bucket 2)
    assert t.iloc[2]["CustomerID"] == "C214"
    assert t.iloc[2]["Bucket"] == 2


def test_r3_switch_only_when_flag_is_switch():
    """Do NOT consolidate items merely because an alternate item name exists. Only Alternate Flag = SWITCH triggers consolidation."""
    im = pd.DataFrame([
        {
            "SKU": "SKU_OLD",
            "Item Name": "Old Product (10/case)",
            "Category": "Cat A",
            "Master Pack Qty": 10,
            "Unit Cost (Rs)": 50,
            "Alternate Item (name)": "New Product (10/case)",
            "Alternate Flag": "SWITCH",
            "Status": "Active",
        },
        {
            "SKU": "SKU_NEW",
            "Item Name": "New Product (10/case)",
            "Category": "Cat A",
            "Master Pack Qty": 10,
            "Unit Cost (Rs)": 50,
            "Alternate Item (name)": None,
            "Alternate Flag": None,
            "Status": "Active",
        },
        {
            "SKU": "SKU_NO_SWITCH",
            "Item Name": "Other Product (10/case)",
            "Category": "Cat B",
            "Master Pack Qty": 10,
            "Unit Cost (Rs)": 50,
            "Alternate Item (name)": "New Product (10/case)",
            "Alternate Flag": np.nan,  # Has alt item name but NOT SWITCH
            "Status": "Active",
        },
    ])
    switch_map, audit_df = build_switch_map(im)
    assert "SKU_OLD" in switch_map
    assert switch_map["SKU_OLD"] == "SKU_NEW"
    assert "SKU_NO_SWITCH" not in switch_map


def test_r3_transitive_switch_chain():
    """Verify chain switches: A -> B and B -> C resolves to A -> C and B -> C."""
    im = pd.DataFrame([
        {
            "SKU": "SKU_A",
            "Item Name": "Product A",
            "Category": "Cat A",
            "Master Pack Qty": 10,
            "Unit Cost (Rs)": 50,
            "Alternate Item (name)": "Product B",
            "Alternate Flag": "SWITCH",
            "Status": "Active",
        },
        {
            "SKU": "SKU_B",
            "Item Name": "Product B",
            "Category": "Cat A",
            "Master Pack Qty": 10,
            "Unit Cost (Rs)": 50,
            "Alternate Item (name)": "Product C",
            "Alternate Flag": "SWITCH",
            "Status": "Active",
        },
        {
            "SKU": "SKU_C",
            "Item Name": "Product C",
            "Category": "Cat A",
            "Master Pack Qty": 10,
            "Unit Cost (Rs)": 50,
            "Alternate Item (name)": None,
            "Alternate Flag": None,
            "Status": "Active",
        },
    ])
    switch_map, _ = build_switch_map(im)
    assert switch_map["SKU_A"] == "SKU_C"
    assert switch_map["SKU_B"] == "SKU_C"


def test_r4_inactive_items_exclusion_and_reporting():
    """Inactive items excluded from main classification; inactive items with stock reported separately."""
    im = pd.DataFrame([
        {
            "SKU": "SKU_INACTIVE_WITH_STOCK",
            "Item Name": "Discontinued Product",
            "Category": "Cat A",
            "Master Pack Qty": 10,
            "Unit Cost (Rs)": 100,
            "Alternate Item (name)": None,
            "Alternate Flag": None,
            "Status": "Inactive",
        },
        {
            "SKU": "SKU_INACTIVE_NO_STOCK",
            "Item Name": "Old Zero Stock",
            "Category": "Cat A",
            "Master Pack Qty": 10,
            "Unit Cost (Rs)": 100,
            "Alternate Item (name)": None,
            "Alternate Flag": None,
            "Status": "Inactive",
        },
        {
            "SKU": "SKU_ACTIVE",
            "Item Name": "Regular Product",
            "Category": "Cat A",
            "Master Pack Qty": 10,
            "Unit Cost (Rs)": 100,
            "Alternate Item (name)": None,
            "Alternate Flag": None,
            "Status": "Active",
        },
    ])
    stock = pd.DataFrame([
        {"SKU": "SKU_INACTIVE_WITH_STOCK", "Qty 0-30 days": 10, "Qty 31-60 days": 0, "Qty 61-90 days": 0, "Qty 91-180 days": 0, "Qty 180+ days": 0},
        {"SKU": "SKU_INACTIVE_NO_STOCK", "Qty 0-30 days": 0, "Qty 31-60 days": 0, "Qty 61-90 days": 0, "Qty 91-180 days": 0, "Qty 180+ days": 0},
        {"SKU": "SKU_ACTIVE", "Qty 0-30 days": 20, "Qty 31-60 days": 0, "Qty 61-90 days": 0, "Qty 91-180 days": 0, "Qty 180+ days": 0},
    ])
    sales = pd.DataFrame([
        {"Month": "Apr-2026", "CustomerID": "C1", "CustomerName": "Cust 1", "Industry": "Cafe", "SKU": "SKU_ACTIVE", "Qty": 20, "Value (Rs)": 2000}
    ])
    cust = pd.DataFrame([{"CustomerID": "C1", "CustomerName": "Cust 1", "Industry": "Cafe", "Area": "North"}])

    res = run_analysis(im, stock, sales, cust)
    items = res["analysis_items"]
    inactive = res["inactive_stock"]

    # Inactive items must NOT appear in main classification items
    assert "SKU_INACTIVE_WITH_STOCK" not in items["SKU"].values
    assert "SKU_INACTIVE_NO_STOCK" not in items["SKU"].values
    assert "SKU_ACTIVE" in items["SKU"].values

    # Inactive item with stock must appear in inactive_stock
    assert "SKU_INACTIVE_WITH_STOCK" in inactive["SKU"].values
    assert "SKU_INACTIVE_NO_STOCK" not in inactive["SKU"].values


def test_r5_strict_classification_order():
    """Verify strict classification hierarchy:
    1. Red List if 6M sales < 1 Master Pack
    2. Otherwise No Action if Aged Qty == 0 OR Months to Clear < 3
    3. Otherwise Push
    """
    im = pd.DataFrame([
        # Case A: Low sales (< 1 Master Pack) -> Red List even with 0 aged stock and low months to clear
        {
            "SKU": "SKU_RED", "Item Name": "Red Item", "Category": "A",
            "Master Pack Qty": 50, "Unit Cost (Rs)": 10, "Alternate Item (name)": None, "Alternate Flag": None, "Status": "Active"
        },
        # Case B: Sufficient sales, Aged Qty == 0, but Months to Clear = 10 -> No Action because Aged Qty == 0
        {
            "SKU": "SKU_NOACT_NO_AGED", "Item Name": "No Aged Stock", "Category": "A",
            "Master Pack Qty": 10, "Unit Cost (Rs)": 10, "Alternate Item (name)": None, "Alternate Flag": None, "Status": "Active"
        },
        # Case C: Sufficient sales, Aged Qty > 0, but Months to Clear = 2 (< 3) -> No Action because Months to Clear < 3
        {
            "SKU": "SKU_NOACT_FAST_CLEAR", "Item Name": "Fast Clearing", "Category": "A",
            "Master Pack Qty": 10, "Unit Cost (Rs)": 10, "Alternate Item (name)": None, "Alternate Flag": None, "Status": "Active"
        },
        # Case D: Sufficient sales, Aged Qty > 0, and Months to Clear >= 3 -> Push
        {
            "SKU": "SKU_PUSH", "Item Name": "Push Item", "Category": "A",
            "Master Pack Qty": 10, "Unit Cost (Rs)": 10, "Alternate Item (name)": None, "Alternate Flag": None, "Status": "Active"
        },
    ])
    stock = pd.DataFrame([
        # SKU_RED: Stock = 10, Aged = 0
        {"SKU": "SKU_RED", "Qty 0-30 days": 10, "Qty 31-60 days": 0, "Qty 61-90 days": 0, "Qty 91-180 days": 0, "Qty 180+ days": 0},
        # SKU_NOACT_NO_AGED: Total = 100, Aged = 0
        {"SKU": "SKU_NOACT_NO_AGED", "Qty 0-30 days": 100, "Qty 31-60 days": 0, "Qty 61-90 days": 0, "Qty 91-180 days": 0, "Qty 180+ days": 0},
        # SKU_NOACT_FAST_CLEAR: Total = 20, Aged = 10. Avg monthly sales = 10 -> Months to Clear = 2 < 3
        {"SKU": "SKU_NOACT_FAST_CLEAR", "Qty 0-30 days": 10, "Qty 31-60 days": 0, "Qty 61-90 days": 0, "Qty 91-180 days": 5, "Qty 180+ days": 5},
        # SKU_PUSH: Total = 100, Aged = 50. Avg monthly sales = 10 -> Months to Clear = 10 >= 3
        {"SKU": "SKU_PUSH", "Qty 0-30 days": 50, "Qty 31-60 days": 0, "Qty 61-90 days": 0, "Qty 91-180 days": 30, "Qty 180+ days": 20},
    ])
    sales = pd.DataFrame([
        {"Month": "Apr-2026", "CustomerID": "C1", "CustomerName": "C1", "Industry": "Cafe", "SKU": "SKU_RED", "Qty": 5, "Value (Rs)": 500},
        {"Month": "Apr-2026", "CustomerID": "C1", "CustomerName": "C1", "Industry": "Cafe", "SKU": "SKU_NOACT_NO_AGED", "Qty": 60, "Value (Rs)": 6000},
        {"Month": "Apr-2026", "CustomerID": "C1", "CustomerName": "C1", "Industry": "Cafe", "SKU": "SKU_NOACT_FAST_CLEAR", "Qty": 60, "Value (Rs)": 6000},
        {"Month": "Apr-2026", "CustomerID": "C1", "CustomerName": "C1", "Industry": "Cafe", "SKU": "SKU_PUSH", "Qty": 60, "Value (Rs)": 6000},
    ])
    cust = pd.DataFrame([{"CustomerID": "C1", "CustomerName": "C1", "Industry": "Cafe", "Area": "North"}])

    res = run_analysis(im, stock, sales, cust)
    items = res["analysis_items"].set_index("SKU")

    assert items.loc["SKU_RED", "Class"] == "Red List"
    assert items.loc["SKU_NOACT_NO_AGED", "Class"] == "No Action"
    assert items.loc["SKU_NOACT_FAST_CLEAR", "Class"] == "No Action"
    assert items.loc["SKU_PUSH", "Class"] == "Push"


def test_customer_targeting_waterfall_and_exclusivity():
    """Verify customer targeting rules:
    - Only Push items targeted
    - Eligible customers (> 100,000 spend) only
    - Mutually exclusive buckets (1 -> 2 -> 3)
    - Missing industry cannot enter Bucket 2
    """
    im = pd.DataFrame([
        {"SKU": "SKU_P", "Item Name": "Push Item", "Category": "Cat A", "Master Pack Qty": 10, "Unit Cost (Rs)": 10, "Alternate Item (name)": None, "Alternate Flag": None, "Status": "Active"},
        {"SKU": "SKU_CAT", "Item Name": "Other Cat A Item", "Category": "Cat A", "Master Pack Qty": 10, "Unit Cost (Rs)": 10, "Alternate Item (name)": None, "Alternate Flag": None, "Status": "Active"},
        {"SKU": "SKU_RED", "Item Name": "Red Item", "Category": "Cat B", "Master Pack Qty": 10, "Unit Cost (Rs)": 10, "Alternate Item (name)": None, "Alternate Flag": None, "Status": "Active"},
    ])
    # SKU_P is Push, SKU_RED is Red List
    stock = pd.DataFrame([
        {"SKU": "SKU_P", "Qty 0-30 days": 0, "Qty 31-60 days": 0, "Qty 61-90 days": 0, "Qty 91-180 days": 50, "Qty 180+ days": 50},
        {"SKU": "SKU_CAT", "Qty 0-30 days": 0, "Qty 31-60 days": 0, "Qty 61-90 days": 0, "Qty 91-180 days": 0, "Qty 180+ days": 0},
        {"SKU": "SKU_RED", "Qty 0-30 days": 10, "Qty 31-60 days": 0, "Qty 61-90 days": 0, "Qty 91-180 days": 0, "Qty 180+ days": 0},
    ])
    sales = pd.DataFrame([
        # C_BOUGHT bought SKU_P (Spend: 150k)
        {"Month": "Apr-2026", "CustomerID": "C_BOUGHT", "CustomerName": "Bought", "Industry": "Cafe", "SKU": "SKU_P", "Qty": 60, "Value (Rs)": 150000},
        # C_SIMILAR is Cafe, never bought SKU_P (Spend: 120k)
        {"Month": "Apr-2026", "CustomerID": "C_SIMILAR", "CustomerName": "Similar", "Industry": "Cafe", "SKU": "SKU_CAT", "Qty": 60, "Value (Rs)": 120000},
        # C_SAME_CAT is Hotel, bought SKU_CAT in same Cat A (Spend: 110k)
        {"Month": "Apr-2026", "CustomerID": "C_SAME_CAT", "CustomerName": "SameCat", "Industry": "Hotel", "SKU": "SKU_CAT", "Qty": 60, "Value (Rs)": 110000},
        # C_NO_IND has missing industry, bought SKU_CAT (Spend: 130k) -> cannot enter B2, enters B3
        {"Month": "Apr-2026", "CustomerID": "C_NO_IND", "CustomerName": "NoInd", "Industry": np.nan, "SKU": "SKU_CAT", "Qty": 60, "Value (Rs)": 130000},
        # C_INELIGIBLE spent <= 100k (Spend: 50k) -> excluded entirely
        {"Month": "Apr-2026", "CustomerID": "C_INELIGIBLE", "CustomerName": "Ineligible", "Industry": "Cafe", "SKU": "SKU_P", "Qty": 20, "Value (Rs)": 50000},
    ])
    cust = pd.DataFrame([
        {"CustomerID": "C_BOUGHT", "CustomerName": "Bought", "Industry": "Cafe", "Area": "Zone 1"},
        {"CustomerID": "C_SIMILAR", "CustomerName": "Similar", "Industry": "Cafe", "Area": "Zone 1"},
        {"CustomerID": "C_SAME_CAT", "CustomerName": "SameCat", "Industry": "Hotel", "Area": "Zone 1"},
        {"CustomerID": "C_NO_IND", "CustomerName": "NoInd", "Industry": np.nan, "Area": "Zone 1"},
        {"CustomerID": "C_INELIGIBLE", "CustomerName": "Ineligible", "Industry": "Cafe", "Area": "Zone 1"},
    ])

    res = run_analysis(im, stock, sales, cust)
    targets = build_customer_targets(
        res["clean_item_master"],
        res["clean_sales"],
        res["analysis_items"],
        customers=cust
    )

    # Red List items must NOT have targets
    assert "SKU_RED" not in targets

    t_p = targets["SKU_P"]
    # Ineligible customer must not appear
    assert "C_INELIGIBLE" not in t_p["CustomerID"].values

    # Check Buckets
    row_bought = t_p[t_p["CustomerID"] == "C_BOUGHT"].iloc[0]
    assert row_bought["Bucket"] == 1

    row_similar = t_p[t_p["CustomerID"] == "C_SIMILAR"].iloc[0]
    assert row_similar["Bucket"] == 2

    row_same_cat = t_p[t_p["CustomerID"] == "C_SAME_CAT"].iloc[0]
    assert row_same_cat["Bucket"] == 3

    row_no_ind = t_p[t_p["CustomerID"] == "C_NO_IND"].iloc[0]
    # Missing industry cannot enter Bucket 2; falls through to Bucket 3
    assert row_no_ind["Bucket"] == 3
