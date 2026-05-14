"""
Domain-specific auto-cleaning strategies.
Applies targeted cleaning based on detected dataset domain.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

import numpy as np
import pandas as pd


class Domain(Enum):
    SALES = "sales"
    CUSTOMER = "customer"
    FINANCIAL = "financial"
    INVENTORY = "inventory"
    HR = "hr"
    MARKETING = "marketing"
    LOGISTICS = "logistics"
    HEALTHCARE = "healthcare"
    ECOMMERCE = "ecommerce"
    GENERAL = "general"


@dataclass
class CleaningStep:
    action: str
    params: Dict[str, Any]
    reason: str
    columns: Optional[List[str]] = None
    optional: bool = False


@dataclass
class DomainStrategy:
    domain: Domain
    name: str
    description: str
    base_steps: List[CleaningStep]
    conditional_steps: List[Tuple[str, List[CleaningStep]]]
    priority_columns: List[str]


class DomainCleaningStrategies:
    """
    Defines domain-specific cleaning strategies.
    Each strategy includes base cleaning steps and conditional steps
    based on detected column patterns.
    """

    @staticmethod
    def get_sales_strategy(profile) -> DomainStrategy:
        """Strategy for sales/transactional data."""
        base_steps = [
            CleaningStep("remove_duplicates", {}, "Remove duplicate transactions"),
            CleaningStep(
                "standardise_dates",
                {"output_format": "%Y-%m-%d"},
                "Standardize all date formats to ISO",
            ),
            CleaningStep("parse_currency", {}, "Extract numeric values from currency"),
            CleaningStep("parse_number_formatted", {}, "Standardize number formats"),
        ]

        conditional_steps = [
            (
                "has_quantity",
                [
                    CleaningStep(
                        "fill_missing",
                        {"strategy": "zero"},
                        "Fill missing quantities with 0",
                    ),
                ],
            ),
            (
                "has_discount",
                [
                    CleaningStep(
                        "clip_outliers",
                        {"method": "iqr", "iqr_factor": 2.0},
                        "Cap extreme discount values",
                    ),
                ],
            ),
        ]

        priority_cols = [
            "order_id",
            "order_date",
            "customer_id",
            "product_id",
            "quantity",
            "price",
            "total",
            "discount",
        ]

        return DomainStrategy(
            domain=Domain.SALES,
            name="Sales Data Cleaner",
            description="Optimized for transactional sales data",
            base_steps=base_steps,
            conditional_steps=conditional_steps,
            priority_columns=priority_cols,
        )

    @staticmethod
    def get_customer_strategy(profile) -> DomainStrategy:
        """Strategy for customer/user data."""
        base_steps = [
            CleaningStep("remove_duplicates", {}, "Remove duplicate customer records"),
            CleaningStep("trim_whitespace", {}, "Clean whitespace in text fields"),
            CleaningStep(
                "standardise_capitalisation",
                {"strategy": "title"},
                "Standardize name capitalization",
            ),
            CleaningStep("validate_email", {}, "Validate email formats"),
        ]

        conditional_steps = [
            (
                "has_phone",
                [
                    CleaningStep(
                        "normalize_phone", {}, "Standardize phone number formats"
                    ),
                ],
            ),
            (
                "has_postal_code",
                [
                    CleaningStep(
                        "validate_postal_code", {}, "Validate postal code formats"
                    ),
                ],
            ),
            (
                "has_age",
                [
                    CleaningStep(
                        "clip_outliers", {"method": "iqr"}, "Cap unrealistic age values"
                    ),
                ],
            ),
            (
                "has_gender",
                [
                    CleaningStep(
                        "normalise_categories", {}, "Standardize gender values"
                    ),
                ],
            ),
        ]

        priority_cols = [
            "customer_id",
            "name",
            "email",
            "phone",
            "address",
            "city",
            "state",
            "country",
            "age",
            "gender",
        ]

        return DomainStrategy(
            domain=Domain.CUSTOMER,
            name="Customer Data Cleaner",
            description="Optimized for customer/contact data",
            base_steps=base_steps,
            conditional_steps=conditional_steps,
            priority_columns=priority_cols,
        )

    @staticmethod
    def get_financial_strategy(profile) -> DomainStrategy:
        """Strategy for financial data."""
        base_steps = [
            CleaningStep("remove_duplicates", {}, "Remove duplicate transactions"),
            CleaningStep(
                "standardise_dates",
                {"output_format": "%Y-%m-%d"},
                "Standardize transaction dates",
            ),
            CleaningStep("parse_currency", {}, "Extract numeric values from amounts"),
            CleaningStep("round_numeric", {"decimals": 2}, "Round to 2 decimal places"),
        ]

        conditional_steps = [
            (
                "has_balance",
                [
                    CleaningStep(
                        "fill_missing",
                        {"strategy": "zero"},
                        "Fill missing balances with 0",
                    ),
                ],
            ),
            (
                "has_negative",
                [
                    CleaningStep(
                        "validate_range",
                        {"min_val": 0},
                        "Flag negative values for review",
                    ),
                ],
            ),
        ]

        priority_cols = [
            "transaction_id",
            "date",
            "amount",
            "balance",
            "account",
            "type",
            "category",
            "description",
        ]

        return DomainStrategy(
            domain=Domain.FINANCIAL,
            name="Financial Data Cleaner",
            description="Optimized for financial records",
            base_steps=base_steps,
            conditional_steps=conditional_steps,
            priority_columns=priority_cols,
        )

    @staticmethod
    def get_inventory_strategy(profile) -> DomainStrategy:
        """Strategy for inventory data."""
        base_steps = [
            CleaningStep("remove_duplicates", {}, "Remove duplicate inventory records"),
            CleaningStep(
                "fill_missing", {"strategy": "zero"}, "Fill missing quantities with 0"
            ),
            CleaningStep("parse_number_formatted", {}, "Standardize number formats"),
        ]

        conditional_steps = [
            (
                "has_expiry",
                [
                    CleaningStep(
                        "standardise_dates",
                        {"output_format": "%Y-%m-%d"},
                        "Standardize expiry date formats",
                    ),
                    CleaningStep("flag_future_dates", {}, "Flag expired items"),
                ],
            ),
            (
                "has_sku",
                [
                    CleaningStep("normalise_categories", {}, "Standardize SKU formats"),
                ],
            ),
        ]

        priority_cols = [
            "item_id",
            "sku",
            "product_name",
            "quantity",
            "on_hand",
            "supplier",
            "reorder_level",
        ]

        return DomainStrategy(
            domain=Domain.INVENTORY,
            name="Inventory Data Cleaner",
            description="Optimized for inventory/stock data",
            base_steps=base_steps,
            conditional_steps=conditional_steps,
            priority_columns=priority_cols,
        )

    @staticmethod
    def get_hr_strategy(profile) -> DomainStrategy:
        """Strategy for HR data."""
        base_steps = [
            CleaningStep("remove_duplicates", {}, "Remove duplicate employee records"),
            CleaningStep(
                "standardise_dates",
                {"output_format": "%Y-%m-%d"},
                "Standardize all dates",
            ),
            CleaningStep(
                "standardise_capitalisation",
                {"strategy": "title"},
                "Standardize name capitalization",
            ),
            CleaningStep(
                "normalise_categories", {}, "Standardize department/position names"
            ),
        ]

        conditional_steps = [
            (
                "has_salary",
                [
                    CleaningStep(
                        "fill_missing",
                        {"strategy": "median"},
                        "Fill missing salaries with median",
                    ),
                    CleaningStep(
                        "clip_outliers", {"method": "iqr"}, "Cap outlier salaries"
                    ),
                ],
            ),
            (
                "has_birth_date",
                [
                    CleaningStep("age_from_date", {}, "Calculate employee ages"),
                    CleaningStep(
                        "clip_outliers", {"method": "iqr"}, "Verify calculated ages"
                    ),
                ],
            ),
        ]

        priority_cols = [
            "employee_id",
            "name",
            "department",
            "position",
            "hire_date",
            "salary",
            "manager",
        ]

        return DomainStrategy(
            domain=Domain.HR,
            name="HR Data Cleaner",
            description="Optimized for human resources data",
            base_steps=base_steps,
            conditional_steps=conditional_steps,
            priority_columns=priority_cols,
        )

    @staticmethod
    def get_marketing_strategy(profile) -> DomainStrategy:
        """Strategy for marketing data."""
        base_steps = [
            CleaningStep("remove_duplicates", {}, "Remove duplicate campaign records"),
            CleaningStep(
                "standardise_dates",
                {"output_format": "%Y-%m-%d"},
                "Standardize campaign dates",
            ),
            CleaningStep("parse_number_formatted", {}, "Standardize numeric metrics"),
            CleaningStep(
                "fill_missing", {"strategy": "zero"}, "Fill missing metrics with 0"
            ),
        ]

        conditional_steps = [
            (
                "has_conversion",
                [
                    CleaningStep(
                        "validate_range",
                        {"min_val": 0, "max_val": 100},
                        "Validate conversion rates",
                    ),
                ],
            ),
        ]

        priority_cols = [
            "campaign_id",
            "date",
            "channel",
            "impressions",
            "clicks",
            "conversions",
            "spend",
            "revenue",
        ]

        return DomainStrategy(
            domain=Domain.MARKETING,
            name="Marketing Data Cleaner",
            description="Optimized for marketing metrics",
            base_steps=base_steps,
            conditional_steps=conditional_steps,
            priority_columns=priority_cols,
        )

    @staticmethod
    def get_logistics_strategy(profile) -> DomainStrategy:
        """Strategy for logistics/shipping data."""
        base_steps = [
            CleaningStep("remove_duplicates", {}, "Remove duplicate shipment records"),
            CleaningStep(
                "standardise_dates",
                {"output_format": "%Y-%m-%d"},
                "Standardize shipping dates",
            ),
            CleaningStep("normalise_categories", {}, "Standardize status values"),
            CleaningStep("validate_phone", {}, "Validate contact numbers"),
        ]

        conditional_steps = [
            (
                "has_tracking",
                [
                    CleaningStep("trim_whitespace", {}, "Clean tracking numbers"),
                ],
            ),
            (
                "has_distance",
                [
                    CleaningStep("round_numeric", {"decimals": 2}, "Round distances"),
                ],
            ),
        ]

        priority_cols = [
            "shipment_id",
            "tracking_number",
            "origin",
            "destination",
            "carrier",
            "status",
            "ship_date",
            "delivery_date",
        ]

        return DomainStrategy(
            domain=Domain.LOGISTICS,
            name="Logistics Data Cleaner",
            description="Optimized for shipping/logistics data",
            base_steps=base_steps,
            conditional_steps=conditional_steps,
            priority_columns=priority_cols,
        )

    @staticmethod
    def get_healthcare_strategy(profile) -> DomainStrategy:
        """Strategy for healthcare data."""
        base_steps = [
            CleaningStep("remove_duplicates", {}, "Remove duplicate patient records"),
            CleaningStep(
                "standardise_dates",
                {"output_format": "%Y-%m-%d"},
                "Standardize medical dates",
            ),
            CleaningStep(
                "standardise_capitalisation",
                {"strategy": "title"},
                "Standardize name capitalization",
            ),
        ]

        conditional_steps = [
            (
                "has_dob",
                [
                    CleaningStep("age_from_date", {}, "Calculate patient ages"),
                    CleaningStep(
                        "clip_outliers", {"method": "iqr"}, "Verify patient ages"
                    ),
                ],
            ),
            (
                "has_vitals",
                [
                    CleaningStep(
                        "clip_outliers",
                        {"method": "iqr", "iqr_factor": 3.0},
                        "Cap extreme vital readings",
                    ),
                ],
            ),
        ]

        priority_cols = [
            "patient_id",
            "name",
            "dob",
            "gender",
            "diagnosis",
            "admission_date",
            "discharge_date",
            "department",
        ]

        return DomainStrategy(
            domain=Domain.HEALTHCARE,
            name="Healthcare Data Cleaner",
            description="Optimized for medical/healthcare data",
            base_steps=base_steps,
            conditional_steps=conditional_steps,
            priority_columns=priority_cols,
        )

    @staticmethod
    def get_ecommerce_strategy(profile) -> DomainStrategy:
        """Strategy for e-commerce data."""
        base_steps = [
            CleaningStep("remove_duplicates", {}, "Remove duplicate orders"),
            CleaningStep(
                "standardise_dates",
                {"output_format": "%Y-%m-%d"},
                "Standardize order dates",
            ),
            CleaningStep("parse_currency", {}, "Extract prices from currency strings"),
            CleaningStep(
                "fill_missing", {"strategy": "zero"}, "Fill missing amounts with 0"
            ),
        ]

        conditional_steps = [
            (
                "has_rating",
                [
                    CleaningStep(
                        "validate_range",
                        {"min_val": 1, "max_val": 5},
                        "Validate rating values",
                    ),
                ],
            ),
            (
                "has_status",
                [
                    CleaningStep(
                        "normalise_categories", {}, "Standardize order status"
                    ),
                ],
            ),
        ]

        priority_cols = [
            "order_id",
            "customer_id",
            "product_id",
            "order_date",
            "quantity",
            "price",
            "total",
            "status",
            "rating",
        ]

        return DomainStrategy(
            domain=Domain.ECOMMERCE,
            name="E-commerce Data Cleaner",
            description="Optimized for online retail data",
            base_steps=base_steps,
            conditional_steps=conditional_steps,
            priority_columns=priority_cols,
        )

    @staticmethod
    def get_general_strategy(profile) -> DomainStrategy:
        """General strategy for unknown data types."""
        base_steps = [
            CleaningStep("remove_duplicates", {}, "Remove duplicate rows"),
            CleaningStep("trim_whitespace", {}, "Clean whitespace"),
            CleaningStep("normalise_categories", {}, "Standardize categorical values"),
        ]

        conditional_steps = [
            (
                "has_dates",
                [
                    CleaningStep(
                        "standardise_dates",
                        {"output_format": "%Y-%m-%d"},
                        "Standardize date formats",
                    ),
                ],
            ),
            (
                "has_currency",
                [
                    CleaningStep(
                        "parse_currency", {}, "Extract numeric values from currency"
                    ),
                ],
            ),
        ]

        return DomainStrategy(
            domain=Domain.GENERAL,
            name="General Data Cleaner",
            description="Universal cleaning for any data type",
            base_steps=base_steps,
            conditional_steps=conditional_steps,
            priority_columns=[],
        )


class SmartAutoCleaner:
    """
    Intelligent auto-cleaning that adapts to dataset domain.
    """

    STRATEGY_GETTERS = {
        Domain.SALES: DomainCleaningStrategies.get_sales_strategy,
        Domain.CUSTOMER: DomainCleaningStrategies.get_customer_strategy,
        Domain.FINANCIAL: DomainCleaningStrategies.get_financial_strategy,
        Domain.INVENTORY: DomainCleaningStrategies.get_inventory_strategy,
        Domain.HR: DomainCleaningStrategies.get_hr_strategy,
        Domain.MARKETING: DomainCleaningStrategies.get_marketing_strategy,
        Domain.LOGISTICS: DomainCleaningStrategies.get_logistics_strategy,
        Domain.HEALTHCARE: DomainCleaningStrategies.get_healthcare_strategy,
        Domain.ECOMMERCE: DomainCleaningStrategies.get_ecommerce_strategy,
        Domain.GENERAL: DomainCleaningStrategies.get_general_strategy,
    }

    def __init__(self):
        self.strategies = self.STRATEGY_GETTERS

    def get_strategy(self, domain: str, profile) -> DomainStrategy:
        """Get the appropriate strategy for a domain."""
        try:
            domain_enum = Domain(domain)
        except ValueError:
            domain_enum = Domain.GENERAL

        getter = self.strategies.get(domain_enum)
        if getter:
            return getter(profile)

        return DomainCleaningStrategies.get_general_strategy(profile)

    def should_apply_condition(
        self, condition: str, df: pd.DataFrame, profile, columns: List[str]
    ) -> bool:
        """Evaluate whether a conditional step should be applied."""
        col_lower = [c.lower() for c in columns]

        condition_checks = {
            "has_quantity": any(
                "qty" in c or "quantity" in c or "count" in c for c in col_lower
            ),
            "has_discount": any("discount" in c or "off" in c for c in col_lower),
            "has_phone": any(
                "phone" in c or "tel" in c or "mobile" in c for c in col_lower
            ),
            "has_postal_code": any("postal" in c or "zip" in c for c in col_lower),
            "has_age": any("age" in c for c in col_lower),
            "has_gender": any("gender" in c or "sex" in c for c in col_lower),
            "has_balance": any("balance" in c for c in col_lower),
            "has_negative": any(
                "debit" in c or "expense" in c or "cost" in c for c in col_lower
            ),
            "has_expiry": any("expir" in c or "valid" in c for c in col_lower),
            "has_sku": any("sku" in c for c in col_lower),
            "has_salary": any(
                "salary" in c or "compensation" in c or "pay" in c for c in col_lower
            ),
            "has_birth_date": any("birth" in c or "dob" in c for c in col_lower),
            "has_conversion": any("conversion" in c or "rate" in c for c in col_lower),
            "has_tracking": any(
                "tracking" in c or "awb" in c or "bol" in c for c in col_lower
            ),
            "has_distance": any(
                "distance" in c or "miles" in c or "km" in c for c in col_lower
            ),
            "has_dob": any("dob" in c or "birth" in c for c in col_lower),
            "has_vitals": any(
                "vital" in c or "bp" in c or "pulse" in c for c in col_lower
            ),
            "has_conversion": any("conversion" in c for c in col_lower),
            "has_rating": any(
                "rating" in c or "review" in c or "stars" in c for c in col_lower
            ),
            "has_status": any("status" in c for c in col_lower),
            "has_dates": len(profile.date_columns) > 0,
            "has_currency": len(
                [
                    p
                    for p in profile.column_profiles.values()
                    if p.detected_format == "currency"
                ]
            )
            > 0,
        }

        return condition_checks.get(condition, False)

    def get_cleaning_steps(self, df: pd.DataFrame, profile) -> List[CleaningStep]:
        """Generate the list of cleaning steps for a dataset."""
        strategy = self.get_strategy(profile.domain_type, profile)
        all_steps = []

        for step in strategy.base_steps:
            all_steps.append(step)

        for condition, conditional in strategy.conditional_steps:
            if self.should_apply_condition(condition, df, profile, df.columns.tolist()):
                all_steps.extend(conditional)

        return all_steps
