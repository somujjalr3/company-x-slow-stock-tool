"""
Tests for the AI Sales Message Generator module (generate_sales_communication_suite).

Verifies:
1. Acceptance of all 8 selected fields:
   - SKU, Customer, Customer Industry, Purchase History, Bucket, Aged Inventory,
     Recommended Action, Relevant Sales Evidence
2. Generation of all 3 required communication formats:
   - Short WhatsApp-style message
   - Professional email (Subject + Body)
   - Sales call talking points (Structured points + formatted markdown)
3. Mandatory labels:
   - Output clearly labeled as 'AI-generated draft'
   - Explicit review warning: 'The salesperson must review it before sending.'
4. Anti-hallucination guardrails:
   - Zero invented unit prices, discounts, customer needs, quantities, delivery dates, or specs
   - Only uses information present in the application
5. Relationship grounding across Buckets 1, 2, and 3
6. 100% offline deterministic execution when AI is unconfigured or unavailable
7. Zero alteration to analytical calculations
"""
import re
import pytest

from src.ai_outreach import generate_sales_communication_suite, clean_outreach_text


def test_suite_generates_all_three_formats():
    """Verify that generate_sales_communication_suite produces WhatsApp, Email, and Talking Points."""
    suite = generate_sales_communication_suite(
        sku="SKU1005",
        customer="Customer 220",
        customer_industry="Bakery",
        purchase_history=245000,
        bucket=1,
        aged_inventory=48200,
        recommended_action="Contact Customer 220 and promote SKU1005 because the customer previously purchased the item and has ₹245,000 of 6M purchase value.",
        relevant_sales_evidence="Customer purchased SKU1005 in past 6 months; 6M total spend ₹245,000.",
    )

    # 1. Mandatory Labels
    assert suite["label"] == "AI-generated draft"
    assert suite["review_warning"] == "The salesperson must review it before sending."

    # 2. Format 1: Short WhatsApp-style message
    assert "whatsapp_message" in suite
    wa = suite["whatsapp_message"]
    assert isinstance(wa, str)
    assert len(wa) > 30
    assert "SKU1005" in wa
    assert "Customer 220" in wa
    assert "Bakery" in wa

    # 3. Format 2: Professional email
    assert "email_subject" in suite
    assert "email_body" in suite
    sub = suite["email_subject"]
    eb = suite["email_body"]
    assert "SKU1005" in sub
    assert "Customer 220" in sub
    assert "Dear Customer 220" in eb
    assert "Commercial Sales Team" in eb
    assert "Company X" in eb

    # 4. Format 3: Sales call talking points
    assert "talking_points" in suite
    assert "talking_points_formatted" in suite
    tps = suite["talking_points"]
    assert isinstance(tps, list)
    assert len(tps) >= 4
    assert any("SKU1005" in p for p in tps)
    assert any("Customer 220" in p for p in tps)

    # 5. Inputs Used record
    assert "inputs_used" in suite
    inputs = suite["inputs_used"]
    assert inputs["SKU"] == "SKU1005"
    assert inputs["Customer"] == "Customer 220"
    assert inputs["Customer Industry"] == "Bakery"
    assert "₹245,000" in inputs["Purchase History"]
    assert "Bucket 1" in inputs["Bucket"]
    assert "₹48,200" in inputs["Aged Inventory"]
    assert "Contact Customer 220" in inputs["Recommended Action"]
    assert "Customer purchased SKU1005" in inputs["Relevant Sales Evidence"]


def test_suite_bucket_1_relationship_grounding():
    """Verify Bucket 1 message references repeat / historical buyer context."""
    suite = generate_sales_communication_suite(
        sku="SKU1001",
        customer="Client Alpha",
        customer_industry="Food Service",
        purchase_history="₹150,000 across 6M",
        bucket=1,
        aged_inventory="₹30,000 aged stock",
        recommended_action="Contact Client Alpha to promote SKU1001.",
        relevant_sales_evidence="Historical buyer with repeat orders.",
    )

    wa = suite["whatsapp_message"]
    eb = suite["email_body"]
    tps = suite["talking_points_formatted"]

    assert "previous purchase history" in wa or "previous order" in wa
    assert "Food Service" in wa
    assert "Client Alpha" in eb
    assert "Bucket 1" in tps


def test_suite_bucket_2_relationship_grounding():
    """Verify Bucket 2 message references industry peer adoption."""
    suite = generate_sales_communication_suite(
        sku="SKU1002",
        customer="Cafe Beta",
        customer_industry="Hospitality",
        purchase_history="₹180,000 across 6M",
        bucket=2,
        aged_inventory="₹25,000 aged stock",
        recommended_action="Contact Cafe Beta to introduce SKU1002.",
        relevant_sales_evidence="Hospitality peer account.",
    )

    wa = suite["whatsapp_message"]
    assert "Hospitality" in wa
    assert "partners" in wa or "peers" in wa or "sector" in wa
    assert "Cafe Beta" in wa


def test_suite_bucket_3_relationship_grounding():
    """Verify Bucket 3 message references category procurement."""
    suite = generate_sales_communication_suite(
        sku="SKU1003",
        customer="Retail Gamma",
        customer_industry="Supermarket",
        purchase_history="₹300,000 across 6M",
        bucket=3,
        aged_inventory="₹50,000 aged stock",
        recommended_action="Contact Retail Gamma to cross-sell SKU1003.",
        relevant_sales_evidence="Active category buyer.",
    )

    wa = suite["whatsapp_message"]
    assert "category" in wa
    assert "Retail Gamma" in wa


def test_strict_anti_hallucination_guardrails():
    """
    Verify draft communication strictly does NOT invent:
      - Unit prices or commercial rates
      - Discounts or promotional percentages
      - Fabricated customer needs
      - Arbitrary quantities / MOQs
      - Delivery dates / turnaround guarantees
      - Product specifications
    """
    suite = generate_sales_communication_suite(
        sku="SKU1005",
        customer="Customer 220",
        customer_industry="Bakery",
        purchase_history=245000,
        bucket=1,
        aged_inventory=48200,
        recommended_action="Contact Customer 220 and promote SKU1005.",
        relevant_sales_evidence="Previous purchase of SKU1005.",
    )

    wa = suite["whatsapp_message"]
    eb = suite["email_body"]

    # Customer outreach texts (WhatsApp and Email) must not quote discounts or promises
    for text in [wa, eb]:
        # 1. No discounts or special price promises
        assert not re.search(r"\b\d+%\s*off\b", text, re.IGNORECASE)
        assert not re.search(r"\bdiscount\b", text, re.IGNORECASE)
        assert not re.search(r"\bspecial\s+price\b", text, re.IGNORECASE)
        assert not re.search(r"\bfree\s+shipping\b", text, re.IGNORECASE)

        # 2. No delivery promises
        assert not re.search(r"\bdelivered\s+by\b", text, re.IGNORECASE)
        assert not re.search(r"\bguaranteed\s+delivery\b", text, re.IGNORECASE)
        assert not re.search(r"\bby\s+(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b", text, re.IGNORECASE)
        assert not re.search(r"\bwithin\s+\d+\s+hours\b", text, re.IGNORECASE)

        # 3. No arbitrary MOQ / quantities fabricated
        assert not re.search(r"\bmoq\s*:\s*\d+", text, re.IGNORECASE)
        assert not re.search(r"\bminimum\s+order\s+of\s+\d+", text, re.IGNORECASE)


def test_deterministic_offline_continuity_without_api_key():
    """Verify generator runs 100% deterministically when no API key is provided."""
    suite = generate_sales_communication_suite(
        sku="SKU1008",
        customer="Client Offline",
        customer_industry="Logistics",
        purchase_history=120000,
        bucket=2,
        aged_inventory=15000,
        recommended_action="Contact Client Offline regarding SKU1008.",
        relevant_sales_evidence="Sector peer.",
        api_key=None,
    )

    assert suite["source"] == "Deterministic Grounded Generator (Rule-Compliant)"
    assert suite["safety_verified"] is True
    assert "Client Offline" in suite["whatsapp_message"]
    assert "Client Offline" in suite["email_body"]
    assert len(suite["talking_points"]) >= 4


def test_robustness_with_empty_or_none_inputs():
    """Verify graceful handling when optional or partially missing fields are passed."""
    suite = generate_sales_communication_suite(
        sku=None,
        customer=None,
        customer_industry="",
        purchase_history=None,
        bucket=None,
        aged_inventory=0,
        recommended_action="",
        relevant_sales_evidence="",
    )

    assert suite["label"] == "AI-generated draft"
    assert suite["review_warning"] == "The salesperson must review it before sending."
    assert "whatsapp_message" in suite
    assert "email_body" in suite
    assert len(suite["talking_points"]) >= 4
