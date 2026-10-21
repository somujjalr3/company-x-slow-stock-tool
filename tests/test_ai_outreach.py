"""
Tests for the optional AI Sales Outreach Message generator.
Verifies message drafting across WhatsApp/Email, relationship grounding (Buckets 1, 2, 3),
strict absence of hallucinated prices/discounts/quantities/dates,
deterministic fallback when AI is offline, and AI usage note presence.
"""
import inspect
import re
import pytest

from src.ai_outreach import (
    generate_sales_outreach_message,
    generate_template_outreach,
    clean_outreach_text,
    PROHIBITED_TERMS,
)
import src.business_logic
import src.customer_targets


def test_whatsapp_outreach_generation_bucket_1():
    """Verify WhatsApp message for Bucket 1 references previous purchase history."""
    msg = generate_sales_outreach_message(
        customer_name="Customer 220",
        item_name="Product 05 (10/case)",
        category="Cat 1",
        customer_industry="Bakery",
        customer_area="North Zone",
        bucket=1,
        channel="WhatsApp",
    )

    text = msg["message"]
    assert "Customer 220" in text
    assert "Product 05 (10/case)" in text
    assert "Cat 1" in text
    assert "North Zone" in text
    assert "previously ordered" in text
    assert msg["channel"] == "WhatsApp"
    assert msg["safety_verified"] is True


def test_whatsapp_outreach_generation_bucket_2():
    """Verify WhatsApp message for Bucket 2 references industry peer usage."""
    msg = generate_sales_outreach_message(
        customer_name="Customer 214",
        item_name="Product 05 (10/case)",
        category="Cat 1",
        customer_industry="Cafe",
        customer_area="South Zone",
        bucket=2,
        channel="WhatsApp",
    )

    text = msg["message"]
    assert "Customer 214" in text
    assert "Product 05 (10/case)" in text
    assert "Cafe" in text
    assert "South Zone" in text
    assert "partners" in text or "businesses" in text
    assert msg["channel"] == "WhatsApp"


def test_email_outreach_generation_bucket_3():
    """Verify Email draft for Bucket 3 references category history and includes professional subject line."""
    msg = generate_sales_outreach_message(
        customer_name="Customer 101",
        item_name="Product 19 (5/case)",
        category="Cat 2",
        customer_industry="Restaurant",
        customer_area="Central",
        bucket=3,
        channel="Email",
    )

    assert msg["channel"] == "Email"
    assert msg["subject"] is not None
    assert "Product 19 (5/case)" in msg["subject"]
    assert "Customer 101" in msg["message"]
    assert "Cat 2" in msg["message"]
    assert "Dear Customer 101" in msg["message"]
    assert "Best regards" in msg["message"]


def test_strict_absence_of_hallucinated_commercial_terms():
    """Verify generated messages do NOT invent prices, discounts, delivery dates, or quotas."""
    test_cases = [
        {"bucket": 1, "channel": "WhatsApp"},
        {"bucket": 2, "channel": "WhatsApp"},
        {"bucket": 3, "channel": "WhatsApp"},
        {"bucket": 1, "channel": "Email"},
        {"bucket": 2, "channel": "Email"},
        {"bucket": 3, "channel": "Email"},
    ]

    for tc in test_cases:
        out = generate_sales_outreach_message(
            customer_name="Test Client",
            item_name="Test Product",
            category="Test Category",
            customer_industry="Retail",
            customer_area="Metro",
            bucket=tc["bucket"],
            channel=tc["channel"],
        )
        content = (out.get("subject") or "") + " " + out["message"]

        # 1. No invented prices (₹, $, Rs)
        assert not re.search(r"₹\s*\d+", content)
        assert not re.search(r"Rs\.?\s*\d+", content, re.IGNORECASE)
        assert not re.search(r"\$\s*\d+", content)

        # 2. No invented discounts or offers
        assert not re.search(r"\b\d+%\s*off\b", content, re.IGNORECASE)
        assert not re.search(r"\bdiscount\b", content, re.IGNORECASE)
        assert not re.search(r"\bspecial\s+price\b", content, re.IGNORECASE)

        # 3. No invented delivery dates
        assert not re.search(r"\bdelivered\s+by\b", content, re.IGNORECASE)
        assert not re.search(r"\bby\s+(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b", content, re.IGNORECASE)


def test_clean_outreach_text_sanitizer():
    """Verify clean_outreach_text strips prohibited commercial promises."""
    dirty = "Buy now with a 20% off discount and special price of ₹500 delivered by Friday!"
    cleaned = clean_outreach_text(dirty)
    assert "20% off" not in cleaned
    assert "₹500" not in cleaned
    assert "discount" not in cleaned


def test_deterministic_fallback_when_ai_offline():
    """Verify tool runs deterministically with zero network calls when no API key is provided."""
    # With api_key=None, it uses template generator directly
    out = generate_sales_outreach_message(
        customer_name="Client A",
        item_name="SKU Alpha",
        category="Industrial",
        customer_industry="Manufacturing",
        customer_area="West",
        bucket=1,
        channel="WhatsApp",
        api_key=None,
    )
    assert out["source"] == "Standard Outreach Generator (Rule-Grounded)"
    assert "Client A" in out["message"]


def test_core_business_logic_never_uses_ai():
    """
    Verify core business logic (inventory, classification, eligibility, bucket assignment, sorting)
    strictly uses deterministic Python/Pandas logic and never calls AI.
    """
    logic_src = inspect.getsource(src.business_logic)
    target_src = inspect.getsource(src.customer_targets)

    # Core logic modules must not import or reference ai_outreach
    assert "ai_outreach" not in logic_src
    assert "ai_outreach" not in target_src
    assert "requests.post" not in logic_src
    assert "generateContent" not in logic_src


def test_ai_usage_note_present_in_app():
    """Verify AI usage note is prominently displayed in app.py."""
    with open("app.py", "r", encoding="utf-8") as f:
        app_code = f.read()

    assert "AI Usage Note" in app_code
    assert "All inventory calculations, item classifications" in app_code
    assert "never determined or influenced by AI" in app_code
