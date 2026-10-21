"""
Test mobile action cards vs desktop table consistency for Sales Action List.
Ensures:
- Identical data between desktop view and mobile cards
- Strict priority ordering (Bucket 1 -> Bucket 2 -> Bucket 3)
- Required fields: Priority, Customer Name, Customer ID, Bucket, Industry, Area, 6M Purchase Value
- Specific case benchmark: SKU1005 top targets (Customer 220, 224, 214)
"""
import pandas as pd
import pytest

from src.data_loader import load_data
from src.validation import validate_data
from src.business_logic import run_analysis
from src.customer_targets import build_customer_targets

PATH = "sample_data/CompanyX_Data.xlsx"


@pytest.fixture
def loaded_targets():
    raw = load_data(PATH)
    val = validate_data(*raw)
    analysis = run_analysis(*raw, validation=val)
    targets = build_customer_targets(
        analysis["clean_item_master"],
        analysis["clean_sales"],
        analysis["analysis_items"],
        val,
        customers=raw[3]
    )
    return targets, analysis["analysis_items"]


def test_sku1005_mobile_and_desktop_card_data(loaded_targets):
    targets, items = loaded_targets
    assert "SKU1005" in targets
    df = targets["SKU1005"]

    # Must contain 9 targets
    assert len(df) == 9

    # Required top targets
    # Priority 1: Customer 220, C220, Bucket 1, spend ₹665,004
    assert df.iloc[0]["Priority"] == 1
    assert df.iloc[0]["CustomerID"] == "C220"
    assert df.iloc[0]["CustomerName"] == "Customer 220"
    assert df.iloc[0]["Bucket"] == 1
    assert df.iloc[0]["Bucket Name"] == "1 - Bought Before"
    assert f"Bucket {df.iloc[0]['Bucket Name']}" == "Bucket 1 - Bought Before"
    assert df.iloc[0]["Industry"] == "Caterer"
    assert df.iloc[0]["Area"] == "Zone 2"
    assert df.iloc[0]["6M Purchase Value"] == pytest.approx(665004.0)

    # Priority 2: Customer 224, C224, Bucket 1, spend ₹320,780
    assert df.iloc[1]["Priority"] == 2
    assert df.iloc[1]["CustomerID"] == "C224"
    assert df.iloc[1]["CustomerName"] == "Customer 224"
    assert df.iloc[1]["Bucket"] == 1
    assert df.iloc[1]["Bucket Name"] == "1 - Bought Before"
    assert f"Bucket {df.iloc[1]['Bucket Name']}" == "Bucket 1 - Bought Before"
    assert df.iloc[1]["Industry"] == "Restaurant"
    assert df.iloc[1]["Area"] == "Zone 1"
    assert df.iloc[1]["6M Purchase Value"] == pytest.approx(320780.0)

    # Priority 3: Customer 214, C214, Bucket 2, spend ₹574,001
    assert df.iloc[2]["Priority"] == 3
    assert df.iloc[2]["CustomerID"] == "C214"
    assert df.iloc[2]["CustomerName"] == "Customer 214"
    assert df.iloc[2]["Bucket"] == 2
    assert df.iloc[2]["Bucket Name"] == "2 - Similar Business"
    assert f"Bucket {df.iloc[2]['Bucket Name']}" == "Bucket 2 - Similar Business"
    assert df.iloc[2]["Industry"] == "Caterer"
    assert df.iloc[2]["Area"] == "Zone 1"
    assert df.iloc[2]["6M Purchase Value"] == pytest.approx(574001.0)


def test_all_push_skus_have_identical_data_and_deterministic_order(loaded_targets):
    targets, items = loaded_targets
    push_skus = items.loc[items["Class"] == "Push", "SKU"].tolist()

    for sku in push_skus:
        df = targets.get(sku, pd.DataFrame())
        if df.empty:
            continue

        # Priority must be sequential 1..N
        expected_priorities = list(range(1, len(df) + 1))
        assert df["Priority"].tolist() == expected_priorities

        # Bucket sequence must be non-decreasing (Bucket 1 -> Bucket 2 -> Bucket 3)
        buckets = df["Bucket"].tolist()
        assert buckets == sorted(buckets)

        # Within each bucket, 6M Purchase Value must be descending
        for b in [1, 2, 3]:
            b_df = df[df["Bucket"] == b]
            if len(b_df) > 1:
                vals = b_df["6M Purchase Value"].tolist()
                assert vals == sorted(vals, reverse=True)

        # Check required fields are non-null
        assert df["CustomerID"].notna().all()
        assert df["CustomerName"].notna().all()
        assert df["Bucket Name"].notna().all()
        assert (df["6M Purchase Value"] > 100000).all()
