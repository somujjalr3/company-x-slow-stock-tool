"""
Centralized Configuration Structure for Company X Slow Stock Action Tool.

Centralizes all configurable parameters across the application:
  1. Red List sales threshold (Default: 6M Sales Qty < 1.0 Master Pack)
  2. Months-to-clear threshold (Default: Months to Clear < 3.0)
  3. Customer eligibility purchase value (Default: 6M Purchase Value > ₹100,000)
  4. Aging threshold (Default: 91+ days)
  5. Risk thresholds (Default: Critical >= 80, High >= 60, Medium >= 30, Low < 30)
  6. Priority thresholds (Default: Critical >= 80, High >= 60, Medium >= 30, Low < 30)

CRITICAL INVARIANTS:
- Default values must EXACTLY match the case requirements.
- Never hard-code these values throughout business logic; reference this structure.
- Configuration changes must never mutate or corrupt raw source data.
- Clear indicators when running 'CASE DEFAULT SETTINGS' vs 'CUSTOM SETTINGS'.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional


@dataclass
class CaseConfig:
    """
    Centralized configuration holding all business rules and operational thresholds.
    Default values match the Company X MBA Case Study requirements exactly.
    """
    # 1. Red List Sales Threshold (Multiplier of Master Pack Qty)
    # Default: 6M Sales Qty < 1.0 Master Pack
    red_list_mp_multiplier: float = 1.0

    # 2. Months-to-Clear Threshold (Runway Cutoff in Months)
    # Default: Months to Clear < 3.0 -> No Action
    months_to_clear_threshold: float = 3.0

    # 3. Customer Eligibility Purchase Value (6M Spend Cutoff in ₹)
    # Default: 6M Purchase Value > ₹100,000
    customer_eligibility_spend: float = 100000.0

    # 4. Aging Days Threshold (Cutoff for Aged Stock in Days)
    # Default: 91+ days (Aging buckets: 91-180 days, 180+ days)
    aging_days_threshold: int = 91

    # 5. Inventory Risk Thresholds (0-100 Score Tiers)
    # Default: Critical >= 80, High >= 60, Medium >= 30, Low < 30
    risk_critical_threshold: int = 80
    risk_high_threshold: int = 60
    risk_medium_threshold: int = 30

    # 6. Sales Priority Thresholds (0-100 Score Tiers for Push Items)
    # Default: Critical >= 80, High >= 60, Medium >= 30, Low < 30
    priority_critical_threshold: int = 80
    priority_high_threshold: int = 60
    priority_medium_threshold: int = 30

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CaseConfig":
        """Instantiate configuration from dictionary with safe fallbacks."""
        if not data:
            return cls()
        valid_fields = cls.__dataclass_fields__.keys()
        clean_kwargs = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**clean_kwargs)

    def is_default(self) -> bool:
        """Check if all parameters match the benchmark case defaults."""
        default = CaseConfig()
        return (
            abs(self.red_list_mp_multiplier - default.red_list_mp_multiplier) < 1e-6
            and abs(self.months_to_clear_threshold - default.months_to_clear_threshold) < 1e-6
            and abs(self.customer_eligibility_spend - default.customer_eligibility_spend) < 1e-6
            and self.aging_days_threshold == default.aging_days_threshold
            and self.risk_critical_threshold == default.risk_critical_threshold
            and self.risk_high_threshold == default.risk_high_threshold
            and self.risk_medium_threshold == default.risk_medium_threshold
            and self.priority_critical_threshold == default.priority_critical_threshold
            and self.priority_high_threshold == default.priority_high_threshold
            and self.priority_medium_threshold == default.priority_medium_threshold
        )

    @property
    def mode_label(self) -> str:
        """User-facing execution mode label."""
        return "CASE DEFAULT SETTINGS" if self.is_default() else "CUSTOM SETTINGS"

    def diff_from_defaults(self) -> List[Dict[str, Any]]:
        """Returns a list of parameters that diverge from the case defaults."""
        default = CaseConfig()
        diffs = []

        param_metadata = [
            ("red_list_mp_multiplier", "Red List Sales Threshold", f"{default.red_list_mp_multiplier:.1f}x MP", f"{self.red_list_mp_multiplier:.1f}x MP"),
            ("months_to_clear_threshold", "Months-to-Clear Threshold", f"{default.months_to_clear_threshold:.1f} months", f"{self.months_to_clear_threshold:.1f} months"),
            ("customer_eligibility_spend", "Customer Eligibility 6M Spend", f"₹{default.customer_eligibility_spend:,.0f}", f"₹{self.customer_eligibility_spend:,.0f}"),
            ("aging_days_threshold", "Aging Days Threshold", f"{default.aging_days_threshold}+ days", f"{self.aging_days_threshold}+ days"),
            ("risk_critical_threshold", "Risk Critical Cutoff", f">= {default.risk_critical_threshold}", f">= {self.risk_critical_threshold}"),
            ("risk_high_threshold", "Risk High Cutoff", f">= {default.risk_high_threshold}", f">= {self.risk_high_threshold}"),
            ("risk_medium_threshold", "Risk Medium Cutoff", f">= {default.risk_medium_threshold}", f">= {self.risk_medium_threshold}"),
            ("priority_critical_threshold", "Priority Critical Cutoff", f">= {default.priority_critical_threshold}", f">= {self.priority_critical_threshold}"),
            ("priority_high_threshold", "Priority High Cutoff", f">= {default.priority_high_threshold}", f">= {self.priority_high_threshold}"),
            ("priority_medium_threshold", "Priority Medium Cutoff", f">= {default.priority_medium_threshold}", f">= {self.priority_medium_threshold}"),
        ]

        for attr, name, def_val, cur_val in param_metadata:
            val_cur = getattr(self, attr)
            val_def = getattr(default, attr)
            if val_cur != val_def:
                diffs.append({
                    "parameter": name,
                    "default_value": def_val,
                    "custom_value": cur_val,
                    "attr": attr,
                })

        return diffs


# Singleton / Factory helpers
DEFAULT_CONFIG = CaseConfig()


def get_default_config() -> CaseConfig:
    """Returns a fresh instance of the benchmark case configuration."""
    return CaseConfig()


def is_case_default(config: Optional[CaseConfig]) -> bool:
    """Helper to verify if a config instance or dict is running case defaults."""
    if config is None:
        return True
    if isinstance(config, dict):
        config = CaseConfig.from_dict(config)
    return config.is_default()


def get_current_case_rules() -> List[Dict[str, str]]:
    """
    Returns the official, static Company X Case Study Rules (R1–R7)
    for reference and comparison on the Settings page.
    """
    return [
        {
            "Rule": "Rule R1: Catalog Scope",
            "Domain": "Item Master",
            "Definition": "Only active commercial items are evaluated. Inactive items are excluded from active sales recommendations.",
            "Case Requirement": "Status == 'Active' required for commercial classification.",
        },
        {
            "Rule": "Rule R2: Master Pack & Cost Integrity",
            "Domain": "Item Master",
            "Definition": "Master Pack Quantity and Unit Cost must be positive non-zero values to ensure valid economic evaluation.",
            "Case Requirement": "Master Pack Qty >= 1; Unit Cost (Rs) > 0.",
        },
        {
            "Rule": "Rule R3: Pack-Size SWITCH Consolidation",
            "Domain": "Item Master & Sales",
            "Definition": "When Alternate Flag = SWITCH, old SKU sales history and physical stock roll up under the new replacement SKU.",
            "Case Requirement": "Old SKU does not remain as a separate analytical item; demand rolls up under new SKU.",
        },
        {
            "Rule": "Rule R4: Inactive Stock Segregation",
            "Domain": "Warehouse Stock",
            "Definition": "Inactive items with physical warehouse inventory are separately tracked and reported in an isolated audit register.",
            "Case Requirement": "Physical capital is audited without diluting active sales queues.",
        },
        {
            "Rule": "Rule R5: Master Slow Stock Classification",
            "Domain": "Decision Engine",
            "Definition": "Applied in strict order:\n1. Red List: 6M Sales Qty < 1 Master Pack\n2. No Action: Aged Qty = 0 OR Months to Clear < 3.0\n3. Push: All remaining items",
            "Case Requirement": "Red List if Sales < 1 MP; No Action if Aged=0 or MTC < 3; otherwise Push.",
        },
        {
            "Rule": "Rule R6: Customer Spend Qualification",
            "Domain": "Customer Targeting",
            "Definition": "Customers must have 6-month purchase turnover > ₹100,000 to qualify for targeted sales outreach.",
            "Case Requirement": "6M Purchase Value > ₹100,000 required for sales calling lists.",
        },
        {
            "Rule": "Rule R7: Priority Waterfall Matching",
            "Domain": "Customer Targeting",
            "Definition": "Qualified customers are waterfalled into 3 affinity tiers:\n• Bucket 1: Direct past buyers of the SKU\n• Bucket 2: Industry affinity (requires valid Industry)\n• Bucket 3: Category buyers",
            "Case Requirement": "Customers with missing Industry cannot enter Bucket 2. No cold pitches without purchase evidence.",
        },
    ]
