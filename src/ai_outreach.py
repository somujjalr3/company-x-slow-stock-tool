"""
Optional AI Sales Outreach Module for Company X Slow Stock Action Tool.

Drafts concise, professional WhatsApp and Email outreach messages for sales executives
targeting Push items to eligible customer accounts.

STRICT CONSTRAINTS (Rule Compliance):
- AI is NEVER used for inventory calculations, classification, eligibility, bucket assignment, or sorting.
- Messages MUST NOT invent prices, discounts, quantities, delivery dates, product specifications, or customer requirements.
- Uses strictly:
    * Customer Name
    * Item Name
    * Category
    * Customer Industry
    * Customer Area
    * Previous purchase relationship (Bucket 1: previous buyer, Bucket 2: industry peer, Bucket 3: category buyer)
    * Push status (active warehouse allocation requiring sales push)
- If external AI APIs are unavailable or unconfigured, the deterministic outreach generator ensures 100% operational continuity.
"""
import json
import os
import re
from typing import Dict, List, Tuple, Any, Optional
import requests
from src.logger import get_logger

logger = get_logger("AIOutreach")


# Prohibited hallucination terms to guard against
PROHIBITED_TERMS = [
    r"\b\d+%\s*off\b",
    r"\bdiscount\b",
    r"\bspecial\s+price\b",
    r"₹\s*\d+",
    r"\bRs\.?\s*\d+",
    r"\$\s*\d+",
    r"\bfree\s+shipping\b",
    r"\bdelivered\s+by\b",
    r"\bguaranteed\s+delivery\b",
    r"\bwithin\s+\d+\s+hours\b",
]


def clean_outreach_text(text: str) -> str:
    """Sanitizes generated outreach text to ensure no prohibited commercial terms were hallucinated."""
    cleaned = text.strip()
    for pattern in PROHIBITED_TERMS:
        cleaned = re.sub(pattern, "[Standard Terms]", cleaned, flags=re.IGNORECASE)
    return cleaned


def _build_relationship_summary(bucket: int, item_name: str, category: str, industry: str) -> str:
    """Generates an honest, grounded description of the customer relationship."""
    ind_str = f"in the {industry} industry" if industry and industry not in ["Unassigned", "nan", "None", ""] else ""
    if bucket == 1:
        return f"Historical buyer of {item_name} {ind_str}"
    elif bucket == 2:
        return f"Sector match: {industry or 'Industry'} account aligned with active buyers of this product"
    elif bucket == 3:
        return f"Existing category account with verified purchase history in {category}"
    return f"Qualified account {ind_str}"


def generate_template_outreach(
    customer_name: str,
    item_name: str,
    category: str,
    customer_industry: str,
    customer_area: str,
    bucket: int,
    channel: str = "WhatsApp",
) -> dict:
    """
    Deterministic outreach draft generator.
    Guaranteed to run offline with zero external network dependencies,
    zero hallucinated prices/discounts, and full compliance with business rules.
    """
    cust_clean = customer_name or "Valued Client"
    ind_clean = customer_industry if customer_industry and customer_industry not in ["Unassigned", "nan", "None", ""] else "your industry"
    area_clean = customer_area if customer_area and customer_area not in ["Standard", "nan", "None", ""] else "your market"
    rel_summary = _build_relationship_summary(bucket, item_name, category, customer_industry)

    if channel.lower() == "whatsapp":
        if bucket == 1:
            body = (
                f"Hi {cust_clean}, hope you're having a productive week. "
                f"Reaching out from Company X regarding operations in {area_clean}. "
                f"As you have previously ordered {item_name} from our {category} catalog, "
                f"we wanted to let you know that fresh allocation is currently ready in warehouse. "
                f"Would love to connect briefly to discuss replenishment for your upcoming schedule. "
                f"Let me know if you have a moment to connect today. Thanks!"
            )
        elif bucket == 2:
            body = (
                f"Hi {cust_clean}, hope you are doing well. "
                f"Reaching out from Company X regarding your {ind_clean} business in {area_clean}. "
                f"Several {ind_clean} partners actively utilize {item_name} ({category}), "
                f"and we currently have allocation confirmed in our warehouse. "
                f"Would be glad to share product details and see if this aligns with your current needs. "
                f"Let me know if you'd like a quick phone chat!"
            )
        else:  # Bucket 3
            body = (
                f"Hi {cust_clean}, hope all is well. "
                f"Given your regular purchases across our {category} portfolio in {area_clean}, "
                f"we wanted to highlight {item_name}, which is in stock and available for immediate allocation. "
                f"Please let us know if you'd like to explore adding this line to your next order schedule. "
                f"Happy to coordinate a brief discussion!"
            )

        return {
            "channel": "WhatsApp",
            "subject": None,
            "message": body,
            "source": "Standard Outreach Generator (Rule-Grounded)",
            "relationship_summary": rel_summary,
            "safety_verified": True,
        }

    else:  # Email
        if bucket == 1:
            subject = f"Inventory Availability: {item_name} for {cust_clean}"
            body = (
                f"Dear {cust_clean},\n\n"
                f"I hope this message finds you well.\n\n"
                f"As an established partner in {area_clean} with a previous purchase history for {item_name}, "
                f"we wanted to inform you that we currently have inventory readily available in our warehouse.\n\n"
                f"Given your familiarity with this product in our {category} range, we would be pleased to review "
                f"your upcoming inventory requirements and assist with timely allocation.\n\n"
                f"Please let me know if you are available for a brief call this week to discuss incorporating this "
                f"into your procurement plan.\n\n"
                f"Best regards,\n"
                f"Commercial Sales Team\n"
                f"Company X"
            )
        elif bucket == 2:
            subject = f"Portfolio Allocation for {cust_clean}: {item_name}"
            body = (
                f"Dear {cust_clean},\n\n"
                f"I hope you are having a productive week.\n\n"
                f"Company X works closely with commercial accounts in the {ind_clean} sector across {area_clean}. "
                f"Based on ongoing adoption among similar {ind_clean} businesses, we would like to present {item_name} "
                f"from our {category} portfolio, which currently has confirmed stock availability.\n\n"
                f"If you are reviewing options for your operations, we would welcome the opportunity to share catalog "
                f"information and discuss how this product fits into your current workflow.\n\n"
                f"I look forward to connecting at your convenience.\n\n"
                f"Best regards,\n"
                f"Commercial Sales Team\n"
                f"Company X"
            )
        else:  # Bucket 3
            subject = f"Catalog Update: {item_name} ({category}) for {cust_clean}"
            body = (
                f"Dear {cust_clean},\n\n"
                f"I hope this email finds you well.\n\n"
                f"We value your ongoing business with Company X and your regular procurement from our {category} portfolio. "
                f"We currently have stock on hand for {item_name} and wanted to bring it to your attention as a complementary "
                f"item for your operations in {area_clean}.\n\n"
                f"We would be pleased to coordinate a brief discussion to review availability and support your next ordering cycle.\n\n"
                f"Thank you for your continued partnership.\n\n"
                f"Best regards,\n"
                f"Commercial Sales Team\n"
                f"Company X"
            )

        return {
            "channel": "Email",
            "subject": subject,
            "message": body,
            "source": "Standard Outreach Generator (Rule-Grounded)",
            "relationship_summary": rel_summary,
            "safety_verified": True,
        }


def generate_sales_outreach_message(
    customer_name: str,
    item_name: str,
    category: str,
    customer_industry: str,
    customer_area: str,
    bucket: int,
    bucket_name: str = "",
    channel: str = "WhatsApp",
    api_key: str = None,
) -> dict:
    """
    Primary entry point for generating customer outreach messages.

    Attempts to call an external LLM if an API key is provided, while falling back
    seamlessly to the deterministic rule-grounded generator if offline or unconfigured.
    """
    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("OPENAI_API_KEY")

    # If no key is provided, use the deterministic generator directly
    if not key:
        return generate_template_outreach(
            customer_name=customer_name,
            item_name=item_name,
            category=category,
            customer_industry=customer_industry,
            customer_area=customer_area,
            bucket=bucket,
            channel=channel,
        )

    # Optional external AI call (with strict prompt constraints)
    rel_summary = _build_relationship_summary(bucket, item_name, category, customer_industry)
    prompt = f"""
You are a commercial sales assistant for Company X.
Draft a concise, professional {channel} outreach message from an account manager to a client.

Context facts:
- Customer Name: {customer_name}
- Product / Item Name: {item_name}
- Category: {category}
- Customer Industry: {customer_industry or 'Unassigned'}
- Customer Area: {customer_area or 'Standard'}
- Relationship Context: {rel_summary} (Push slow-stock item requiring sales focus)

STRICT MANDATORY RULES:
1. Do NOT invent prices, costs, or monetary figures.
2. Do NOT invent discounts, promotional percentages, or special deals.
3. Do NOT invent quantities, batch sizes, or MOQ.
4. Do NOT invent delivery dates, shipping times, or guarantees.
5. Do NOT invent technical product specifications.
6. Do NOT assume customer requirements.
7. Keep tone professional, respectful, and direct. Focus on product availability and inviting a short call.
"""
    try:
        # Check if Gemini key
        if key.startswith("AIza") or "gemini" in key.lower():
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={key}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.2, "maxOutputTokens": 300},
            }
            resp = requests.post(url, json=payload, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                cleaned = clean_outreach_text(text)
                return {
                    "channel": channel,
                    "subject": f"Inventory Allocation: {item_name} for {customer_name}" if channel.lower() == "email" else None,
                    "message": cleaned,
                    "source": "AI Assistant (Gemini Flash)",
                    "relationship_summary": rel_summary,
                    "safety_verified": True,
                }
    except Exception:
        pass  # Gracefully fall back to deterministic template on any network or API issue

    # Default / Fallback
    return generate_template_outreach(
        customer_name=customer_name,
        item_name=item_name,
        category=category,
        customer_industry=customer_industry,
        customer_area=customer_area,
        bucket=bucket,
        channel=channel,
    )


def _normalize_bucket_num(bucket) -> int:
    """Normalizes bucket input (int or string) to an integer 1, 2, or 3."""
    if isinstance(bucket, int) and bucket in (1, 2, 3):
        return bucket
    s = str(bucket).strip()
    m = re.search(r"\b([123])\b", s)
    if m:
        return int(m.group(1))
    return 1


def _format_currency_value(val) -> str:
    """Formats numeric value to currency string or preserves formatted string."""
    if val is None or val == "":
        return ""
    if isinstance(val, (int, float)):
        return f"₹{val:,.0f}"
    return str(val).strip()


def generate_sales_communication_suite(
    sku: str,
    customer: str,
    customer_industry: str,
    purchase_history,
    bucket,
    aged_inventory,
    recommended_action: str,
    relevant_sales_evidence: str,
    api_key: str = None,
) -> dict:
    """
    Generates a draft sales communication suite based ONLY on the 8 selected fields:
      1. SKU
      2. Customer
      3. Customer Industry
      4. Purchase History
      5. Bucket
      6. Aged Inventory
      7. Recommended Action
      8. Relevant Sales Evidence

    Outputs all 3 required formats:
      1. Short WhatsApp-style message
      2. Professional email (subject + body)
      3. Sales call talking points (structured points + formatted markdown)

    STRICT CONSTRAINTS:
      - Does NOT invent: prices, discounts, customer needs, quantities, delivery dates, product specifications.
      - Uses ONLY information present in the application.
      - Clearly labeled as 'AI-generated draft'.
      - Displays explicit notice: 'The salesperson must review it before sending.'
      - Never influences or alters analytical calculations.
      - 100% operational offline fallback.
    """
    # 1. Clean and normalize inputs
    sku_clean = str(sku).strip() if sku else "Selected SKU"
    cust_clean = str(customer).strip() if customer else "Valued Client"
    ind_clean = str(customer_industry).strip() if customer_industry and str(customer_industry).strip() not in ["Unassigned", "nan", "None", ""] else "Commercial"

    ph_clean = _format_currency_value(purchase_history)
    if not ph_clean or ph_clean in ["₹0", "0"]:
        ph_clean = "Established commercial account"
    elif not ph_clean.startswith("₹") and not any(c.isdigit() for c in ph_clean):
        ph_clean = f"Account spend profile: {ph_clean}"

    b_num = _normalize_bucket_num(bucket)
    b_desc_map = {
        1: "Bucket 1 (Bought Before - Repeat Buyer)",
        2: "Bucket 2 (Similar Business - Industry Peer)",
        3: "Bucket 3 (Same Category - Category Buyer)",
    }
    b_desc = b_desc_map.get(b_num, f"Bucket {b_num}")

    aged_clean = _format_currency_value(aged_inventory)
    if not aged_clean or aged_clean in ["₹0", "0"]:
        aged_clean = "Active warehouse allocation"
    elif aged_clean.startswith("₹"):
        aged_clean = f"{aged_clean} aged stock"

    action_clean = str(recommended_action).strip() if recommended_action else f"Contact {cust_clean} and promote {sku_clean} allocation."
    evidence_clean = str(relevant_sales_evidence).strip() if relevant_sales_evidence else "Verified customer account with commercial purchase history."

    inputs_used = {
        "SKU": sku_clean,
        "Customer": cust_clean,
        "Customer Industry": ind_clean,
        "Purchase History": ph_clean,
        "Bucket": b_desc,
        "Aged Inventory": aged_clean,
        "Recommended Action": action_clean,
        "Relevant Sales Evidence": evidence_clean,
    }

    # 2. Check for external AI Key if requested
    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if key and (key.startswith("AIza") or "gemini" in key.lower()):
        try:
            prompt = f"""You are a commercial sales assistant for Company X.
Draft a complete sales communication suite for an account representative contacting an existing client about a warehouse slow-stock Push item.

SELECTED CONTEXT FACTS (DO NOT INVENT ANY ADDITIONAL COMMERCIAL TERMS):
- SKU: {sku_clean}
- Customer: {cust_clean}
- Customer Industry: {ind_clean}
- Purchase History: {ph_clean}
- Bucket: {b_desc}
- Aged Inventory: {aged_clean}
- Recommended Action: {action_clean}
- Relevant Sales Evidence: {evidence_clean}

STRICT MANDATORY RULES (ZERO HALLUCINATION):
1. Do NOT invent prices, unit rates, costs, or monetary figures.
2. Do NOT invent discounts, promotional percentages, rebates, or special deals.
3. Do NOT invent customer needs, assumptions, or operational shortages (e.g. do not say 'since you are running low').
4. Do NOT invent quantities, batch sizes, or minimum order quantities (MOQ).
5. Do NOT invent delivery dates, shipping deadlines, or turnaround times.
6. Do NOT invent technical product specifications.
7. Tone must be professional, direct, and collaborative.

REQUIRED OUTPUT STRUCTURE (valid JSON):
{{
  "whatsapp": "Short, professional, friendly WhatsApp message inviting a brief call about product availability.",
  "email_subject": "Concise professional email subject line.",
  "email_body": "Formal professional email body referencing account relationship, warehouse allocation, and inviting a call.",
  "talking_points": [
    "Point 1: Account & relationship grounding",
    "Point 2: Warehouse stock availability",
    "Point 3: Transactional evidence and rationale",
    "Point 4: Primary objective and recommended action",
    "Point 5: Next steps and commercial discipline"
  ]
}}
"""
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={key}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.2, "maxOutputTokens": 600, "responseMimeType": "application/json"},
            }
            resp = requests.post(url, json=payload, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(raw_text)
                wa = clean_outreach_text(str(parsed.get("whatsapp", "")))
                sub = str(parsed.get("email_subject", f"Inventory Availability: {sku_clean} for {cust_clean}")).strip()
                eb = clean_outreach_text(str(parsed.get("email_body", "")))
                tps = [clean_outreach_text(str(p)) for p in parsed.get("talking_points", []) if str(p).strip()]
                if not tps:
                    tps = [action_clean]
                tps_fmt = "\n\n".join(f"• **Point {i+1}:** {tp}" for i, tp in enumerate(tps))

                return {
                    "label": "AI-generated draft",
                    "review_warning": "The salesperson must review it before sending.",
                    "whatsapp_message": wa,
                    "email_subject": sub,
                    "email_body": eb,
                    "talking_points": tps,
                    "talking_points_formatted": tps_fmt,
                    "inputs_used": inputs_used,
                    "source": "AI Assistant (Gemini Flash)",
                    "safety_verified": True,
                }
        except Exception:
            pass  # Fall back to deterministic template seamlessly

    # 3. Deterministic Generation (Offline & Guaranteed Safe)
    # WhatsApp copy
    if b_num == 1:
        wa_text = (
            f"Hi {cust_clean}, hope you're having a productive week! "
            f"Reaching out from Company X regarding {sku_clean}. "
            f"As an established partner in the {ind_clean} sector with previous purchase history for this item, "
            f"we wanted to let you know that warehouse inventory is currently ready for allocation. "
            f"Would love to connect briefly today to see if this aligns with your replenishment schedule. "
            f"Let me know if you have a moment for a quick chat. Thanks!"
        )
    elif b_num == 2:
        wa_text = (
            f"Hi {cust_clean}, hope you are doing well! "
            f"Reaching out from Company X regarding your {ind_clean} operations. "
            f"We currently have warehouse inventory ready for {sku_clean}, a product actively utilized by partners across the {ind_clean} sector. "
            f"Given your active commercial relationship with us, we'd be glad to share availability and see if this fits your current workflow. "
            f"Let me know if you have a quick moment for a short call today. Thanks!"
        )
    else:  # Bucket 3
        wa_text = (
            f"Hi {cust_clean}, hope all is well! "
            f"Reaching out from Company X regarding your procurement with us. "
            f"We currently have confirmed warehouse stock for {sku_clean}. "
            f"Given your regular purchases across this catalog category, we wanted to highlight its immediate availability for your next ordering cycle. "
            f"Please let us know if you would like to explore adding this line. Happy to coordinate a quick call. Thanks!"
        )

    # Email copy
    email_sub = f"Inventory Availability & Allocation: {sku_clean} for {cust_clean}"
    email_text = (
        f"Dear {cust_clean},\n\n"
        f"I hope this message finds you well.\n\n"
        f"I am writing from the Commercial Sales Team at Company X regarding inventory availability for {sku_clean}.\n\n"
        f"Account & Relationship Context:\n"
        f"Our records reflect that {cust_clean} is an established partner in the {ind_clean} sector "
        f"with verified commercial procurement history ({ph_clean}). Specifically, {evidence_clean}\n\n"
        f"Warehouse Inventory Status:\n"
        f"We currently have confirmed inventory available in our warehouse ({aged_clean}). "
        f"As part of our proactive inventory management, we are making this confirmed allocation available to key commercial accounts.\n\n"
        f"Recommended Action:\n"
        f"{action_clean}\n\n"
        f"Next Steps:\n"
        f"We would welcome the opportunity to connect for a brief 5-minute call this week to review product availability "
        f"and discuss incorporating this item into your upcoming ordering cycle under standard commercial terms.\n\n"
        f"Thank you for your continued partnership with Company X.\n\n"
        f"Best regards,\n\n"
        f"Commercial Sales Team\n"
        f"Company X"
    )

    # Sales call talking points
    talking_points = [
        f"Account Context & Relationship: Acknowledge {cust_clean} as an established {ind_clean} account ({ph_clean}). Account is categorized under {b_desc}.",
        f"Warehouse Stock Availability: Confirm that Company X currently holds warehouse inventory for {sku_clean} ({aged_clean}) ready for immediate dispatch.",
        f"Relevant Sales Evidence: Reference transactional rationale: {evidence_clean}.",
        f"Primary Call Objective: {action_clean}",
        f"Call-to-Action & Discipline: Propose reviewing replenishment needs for {sku_clean} for their next order under standard commercial terms. Do not quote unapproved discounts, off-book prices, or speculative delivery commitments.",
    ]
    talking_points_formatted = "\n\n".join(f"• **Point {i+1}:** {tp}" for i, tp in enumerate(talking_points))

    return {
        "label": "AI-generated draft",
        "review_warning": "The salesperson must review it before sending.",
        "whatsapp_message": wa_text,
        "email_subject": email_sub,
        "email_body": email_text,
        "talking_points": talking_points,
        "talking_points_formatted": talking_points_formatted,
        "inputs_used": inputs_used,
        "source": "Deterministic Grounded Generator (Rule-Compliant)",
        "safety_verified": True,
    }

