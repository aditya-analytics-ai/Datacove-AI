"""
Domain-Specific Cleaning Rules
Specialized cleaning functions for different data domains.
"""

import re
import pandas as pd
import numpy as np
from typing import Any, Optional, Dict, List


class HealthcareCleaner:
    """Cleaning functions for healthcare data."""

    ICD10_PATTERN = r"^[A-Z]\d{2}(\.\d{1,2})?$"
    SSN_PATTERN = r"^\d{3}-\d{2}-\d{4}$"
    PHONE_PATTERN = r"^\+?1?[\s.-]?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}$"
    NPI_PATTERN = r"^\d{10}$"

    @staticmethod
    def clean_icd_code(value: Any) -> Optional[str]:
        """Validate and clean ICD-10 codes."""
        if pd.isna(value) or str(value).strip() == "":
            return None
        val = str(value).strip().upper()
        if re.match(HealthcareCleaner.ICD10_PATTERN, val):
            return val
        return val

    @staticmethod
    def clean_ssn(value: Any) -> Optional[str]:
        """Mask SSN for privacy (show last 4 digits only)."""
        if pd.isna(value) or str(value).strip() == "":
            return None
        val = str(value).strip()
        if re.match(HealthcareCleaner.SSN_PATTERN, val):
            return f"***-**-{val[-4:]}"
        return val

    @staticmethod
    def clean_npi(value: Any) -> Optional[str]:
        """Validate NPI (National Provider Identifier)."""
        if pd.isna(value):
            return None
        val = str(value).strip()
        digits = re.sub(r"\D", "", val)
        if len(digits) == 10:
            return digits
        return val

    @staticmethod
    def clean_medication(value: Any) -> Optional[str]:
        """Standardize medication names."""
        if pd.isna(value) or str(value).strip() == "":
            return None
        val = str(value).strip().lower()
        val = re.sub(r"\s+", " ", val)
        return val.title()

    @staticmethod
    def clean_blood_type(value: Any) -> Optional[str]:
        """Standardize blood type values."""
        if pd.isna(value) or str(value).strip() == "":
            return None
        val = str(value).strip().upper()
        valid_types = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
        for blood_type in valid_types:
            if blood_type in val:
                return blood_type
        return val

    @staticmethod
    def clean_dob(value: Any) -> Optional[str]:
        """Clean and validate date of birth."""
        if pd.isna(value):
            return None
        try:
            date = pd.to_datetime(value)
            if 1900 <= date.year <= 2025:
                return date.strftime("%Y-%m-%d")
        except:
            pass
        return str(value)


class FinancialCleaner:
    """Cleaning functions for financial data."""

    AMOUNT_PATTERN = r"^\$?[\d,]+\.?\d{0,2}$"
    ACCOUNT_PATTERN = r"^\d{4,17}$"
    ROUTING_PATTERN = r"^\d{9}$"
    CC_PATTERN = r"^\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}$"
    IBAN_PATTERN = r"^[A-Z]{2}\d{2}[A-Z0-9]{4,30}$"

    @staticmethod
    def clean_amount(value: Any) -> Optional[float]:
        """Convert amount strings to numeric."""
        if pd.isna(value):
            return None
        val = str(value).strip()
        val = val.replace("$", "").replace(",", "").replace(" ", "")
        try:
            return float(val)
        except ValueError:
            return None

    @staticmethod
    def clean_account_number(value: Any) -> Optional[str]:
        """Mask account number (show last 4 digits)."""
        if pd.isna(value):
            return None
        val = str(value).strip()
        digits = re.sub(r"\D", "", val)
        if len(digits) >= 4:
            return f"****{digits[-4:]}"
        return val

    @staticmethod
    def clean_iban(value: Any) -> Optional[str]:
        """Validate and format IBAN."""
        if pd.isna(value):
            return None
        val = str(value).strip().upper().replace(" ", "")
        if re.match(FinancialCleaner.IBAN_PATTERN, val):
            formatted = " ".join([val[i : i + 4] for i in range(0, len(val), 4)])
            return formatted
        return val

    @staticmethod
    def clean_currency(value: Any) -> Optional[float]:
        """Convert currency strings to numeric, handling multiple formats."""
        if pd.isna(value):
            return None
        val = str(value).strip()
        currencies = ["$", "€", "£", "¥", "₹", "₽", "₿"]
        for curr in currencies:
            val = val.replace(curr, "")
        val = val.replace(",", "").strip()
        try:
            return float(val)
        except ValueError:
            return None

    @staticmethod
    def clean_transaction_type(value: Any) -> Optional[str]:
        """Standardize transaction types."""
        if pd.isna(value) or str(value).strip() == "":
            return None
        val = str(value).strip().lower()
        if "credit" in val or "deposit" in val:
            return "credit"
        elif "debit" in val or "withdraw" in val or "payment" in val:
            return "debit"
        elif "transfer" in val:
            return "transfer"
        return val.title()

    @staticmethod
    def clean_card_number(value: Any) -> Optional[str]:
        """Mask card number (show last 4 digits)."""
        if pd.isna(value):
            return None
        val = str(value).strip()
        digits = re.sub(r"\D", "", val)
        if len(digits) >= 4:
            return f"****-****-****-{digits[-4:]}"
        return val


class EcommerceCleaner:
    """Cleaning functions for e-commerce data."""

    SKU_PATTERN = r"^[A-Z0-9]{4,20}$"

    @staticmethod
    def clean_sku(value: Any) -> Optional[str]:
        """Standardize SKU format."""
        if pd.isna(value) or str(value).strip() == "":
            return None
        val = str(value).strip().upper()
        val = re.sub(r"[^A-Z0-9-]", "", val)
        return val

    @staticmethod
    def clean_product_name(value: Any) -> Optional[str]:
        """Clean product names."""
        if pd.isna(value) or str(value).strip() == "":
            return None
        val = str(value).strip()
        val = re.sub(r"\s+", " ", val)
        val = re.sub(r"[^a-zA-Z0-9\s\-&]", "", val)
        return val.title()

    @staticmethod
    def clean_category(value: Any) -> Optional[str]:
        """Standardize category names."""
        if pd.isna(value) or str(value).strip() == "":
            return None
        val = str(value).strip().lower()
        val = re.sub(r"[^a-z0-9\s]", "", val)
        return val.title()

    @staticmethod
    def clean_rating(value: Any) -> Optional[float]:
        """Convert rating to numeric (1-5 scale)."""
        if pd.isna(value):
            return None
        val = str(value).strip()
        val = val.replace(" stars", "").replace("star", "").strip()
        try:
            rating = float(val)
            if 0 <= rating <= 5:
                return rating
            elif rating > 5:
                return rating / 20
        except ValueError:
            pass
        return None


class HRCleaner:
    """Cleaning functions for HR data."""

    @staticmethod
    def clean_employee_id(value: Any) -> Optional[str]:
        """Standardize employee ID format."""
        if pd.isna(value) or str(value).strip() == "":
            return None
        val = str(value).strip().upper()
        val = re.sub(r"[^A-Z0-9-]", "", val)
        return val

    @staticmethod
    def clean_department(value: Any) -> Optional[str]:
        """Standardize department names."""
        if pd.isna(value) or str(value).strip() == "":
            return None
        val = str(value).strip().lower()
        dept_map = {
            "hr": "Human Resources",
            "it": "Information Technology",
            "sales": "Sales",
            "marketing": "Marketing",
            "finance": "Finance",
            "ops": "Operations",
            "operations": "Operations",
        }
        for key, standardized in dept_map.items():
            if key in val:
                return standardized
        return val.title()

    @staticmethod
    def clean_salary(value: Any) -> Optional[float]:
        """Convert salary to numeric."""
        if pd.isna(value):
            return None
        val = str(value).strip()
        val = val.replace("$", "").replace(",", "").replace(" ", "")
        try:
            return float(val)
        except ValueError:
            return None

    @staticmethod
    def clean_performance_rating(value: Any) -> Optional[str]:
        """Standardize performance ratings."""
        if pd.isna(value) or str(value).strip() == "":
            return None
        val = str(value).strip().lower()
        if any(
            x in val for x in ["exceed", "exceeds", "exceptional", "5", "outstanding"]
        ):
            return "Exceeds Expectations"
        elif any(x in val for x in ["meets", "satisfactory", "3", "4", "good"]):
            return "Meets Expectations"
        elif any(x in val for x in ["below", "needs", "improvement", "1", "2", "poor"]):
            return "Needs Improvement"
        return val.title()


class LogisticsCleaner:
    """Cleaning functions for logistics data."""

    TRACKING_PATTERN = r"^[A-Z0-9]{10,30}$"
    ZIP_PATTERN = r"^\d{5}(-\d{4})?$"

    @staticmethod
    def clean_tracking_number(value: Any) -> Optional[str]:
        """Standardize tracking number format."""
        if pd.isna(value) or str(value).strip() == "":
            return None
        val = str(value).strip().upper()
        val = re.sub(r"[^A-Z0-9]", "", val)
        return val

    @staticmethod
    def clean_weight(value: Any) -> Optional[float]:
        """Convert weight to numeric (standardize to kg)."""
        if pd.isna(value):
            return None
        val = str(value).strip().lower()
        try:
            if "lb" in val or "pound" in val:
                num = float(re.sub(r"[^0-9.]", "", val))
                return num * 0.453592
            elif "kg" in val or "kilogram" in val:
                return float(re.sub(r"[^0-9.]", "", val))
            else:
                return float(re.sub(r"[^0-9.]", "", val))
        except ValueError:
            return None

    @staticmethod
    def clean_dimensions(value: Any) -> Optional[str]:
        """Standardize dimensions format."""
        if pd.isna(value) or str(value).strip() == "":
            return None
        val = str(value).strip()
        val = re.sub(r"\s*x\s*", " x ", val)
        return val

    @staticmethod
    def clean_shipping_status(value: Any) -> Optional[str]:
        """Standardize shipping status."""
        if pd.isna(value) or str(value).strip() == "":
            return None
        val = str(value).strip().lower()
        if any(x in val for x in ["delivered", "complete", "completed"]):
            return "Delivered"
        elif any(x in val for x in ["transit", "shipped", "in transit", "on the way"]):
            return "In Transit"
        elif any(x in val for x in ["pending", "processing", "waiting"]):
            return "Pending"
        elif any(x in val for x in ["cancel", "cancelled"]):
            return "Cancelled"
        return val.title()


class InventoryCleaner:
    """Cleaning functions for inventory data."""

    SKU_PATTERN = r"^[A-Z0-9-]{4,30}$"
    UPC_PATTERN = r"^\d{12,14}$"

    @staticmethod
    def clean_sku(value: Any) -> Optional[str]:
        """Standardize SKU format."""
        if pd.isna(value) or str(value).strip() == "":
            return None
        val = str(value).strip().upper()
        val = re.sub(r"[^A-Z0-9-]", "", val)
        return val

    @staticmethod
    def clean_upc(value: Any) -> Optional[str]:
        """Validate and format UPC/EAN codes."""
        if pd.isna(value):
            return None
        val = str(value).strip()
        digits = re.sub(r"\D", "", val)
        if len(digits) in [12, 13, 14]:
            return digits
        return val

    @staticmethod
    def clean_quantity(value: Any) -> Optional[int]:
        """Convert quantity to integer."""
        if pd.isna(value):
            return None
        try:
            return int(float(str(value).strip()))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def clean_unit_price(value: Any) -> Optional[float]:
        """Convert unit price to numeric."""
        if pd.isna(value):
            return None
        val = str(value).strip()
        val = val.replace("$", "").replace(",", "").replace(" ", "")
        try:
            return float(val)
        except ValueError:
            return None

    @staticmethod
    def clean_stock_status(value: Any) -> Optional[str]:
        """Standardize stock status."""
        if pd.isna(value) or str(value).strip() == "":
            return None
        val = str(value).strip().lower()
        if any(x in val for x in ["in stock", "available", "instock"]):
            return "In Stock"
        elif any(
            x in val for x in ["out of stock", "outofstock", "oos", "unavailable"]
        ):
            return "Out of Stock"
        elif any(x in val for x in ["low stock", "low", "limited"]):
            return "Low Stock"
        elif any(x in val for x in ["discontinued", "end of life"]):
            return "Discontinued"
        return val.title()

    @staticmethod
    def clean_location(value: Any) -> Optional[str]:
        """Standardize warehouse/location codes."""
        if pd.isna(value) or str(value).strip() == "":
            return None
        val = str(value).strip().upper()
        val = re.sub(r"[^A-Z0-9-]", "-", val)
        val = re.sub(r"-+", "-", val).strip("-")
        return val


class IoTCleaner:
    """Cleaning functions for IoT/sensor data."""

    MAC_PATTERN = r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$"
    IP_PATTERN = r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$"
    TIMESTAMP_PATTERN = r"^\d{10,13}$"

    @staticmethod
    def clean_sensor_value(value: Any) -> Optional[float]:
        """Convert sensor reading to numeric."""
        if pd.isna(value):
            return None
        val = str(value).strip()
        val = val.replace(",", "").replace(" ", "")
        try:
            return float(val)
        except ValueError:
            return None

    @staticmethod
    def clean_mac_address(value: Any) -> Optional[str]:
        """Standardize MAC address format."""
        if pd.isna(value) or str(value).strip() == "":
            return None
        val = str(value).strip().upper()
        val = re.sub(r"[^0-9A-F]", "", val)
        if len(val) == 12:
            return ":".join([val[i : i + 2] for i in range(0, 12, 2)])
        return str(value)

    @staticmethod
    def clean_ip_address(value: Any) -> Optional[str]:
        """Validate IP address format."""
        if pd.isna(value) or str(value).strip() == "":
            return None
        val = str(value).strip()
        parts = val.split(".")
        if len(parts) == 4:
            try:
                valid = all(0 <= int(p) <= 255 for p in parts)
                if valid:
                    return val
            except ValueError:
                pass
        return val

    @staticmethod
    def clean_timestamp(value: Any) -> Optional[str]:
        """Convert timestamp to ISO format."""
        if pd.isna(value):
            return None
        val = str(value).strip()
        try:
            if len(val) == 13:
                return pd.to_datetime(int(val), unit="ms").strftime("%Y-%m-%d %H:%M:%S")
            elif len(val) == 10:
                return pd.to_datetime(int(val), unit="s").strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError, OSError):
            pass
        return str(value)

    @staticmethod
    def clean_device_id(value: Any) -> Optional[str]:
        """Standardize device ID format."""
        if pd.isna(value) or str(value).strip() == "":
            return None
        val = str(value).strip().upper()
        val = re.sub(r"[^A-Z0-9]", "", val)
        return val

    @staticmethod
    def clean_battery_level(value: Any) -> Optional[float]:
        """Convert battery level to percentage (0-100)."""
        if pd.isna(value):
            return None
        val = str(value).strip().replace("%", "").replace(" ", "")
        try:
            level = float(val)
            if level > 1:
                level = level / 100
            return max(0, min(100, level * 100))
        except ValueError:
            return None


class RealEstateCleaner:
    """Cleaning functions for real estate data."""

    AREA_PATTERN = r"^\d+(\.\d+)?\s*(sqft|sf|sq\.?\s*ft)?$"
    ZIP_PATTERN = r"^\d{5}(-\d{4})?$"

    @staticmethod
    def clean_property_address(value: Any) -> Optional[str]:
        """Clean property address."""
        if pd.isna(value) or str(value).strip() == "":
            return None
        val = str(value).strip()
        val = re.sub(r"\s+", " ", val)
        return val.title()

    @staticmethod
    def clean_price(value: Any) -> Optional[float]:
        """Convert price to numeric."""
        if pd.isna(value):
            return None
        val = str(value).strip()
        val = val.replace("$", "").replace(",", "").replace(" ", "")
        try:
            return float(val)
        except ValueError:
            return None

    @staticmethod
    def clean_area_sqft(value: Any) -> Optional[float]:
        """Convert area to numeric sqft."""
        if pd.isna(value):
            return None
        val = str(value).strip().lower()
        val = val.replace(",", "").replace(" ", "")
        num_match = re.search(r"[\d.]+", val)
        if num_match:
            num = float(num_match.group())
            if "sqm" in val or "m2" in val or "meter" in val:
                return num * 10.764
            return num
        return None

    @staticmethod
    def clean_bedrooms(value: Any) -> Optional[int]:
        """Convert bedroom count to integer."""
        if pd.isna(value):
            return None
        val = str(value).strip().lower()
        if "studio" in val or "0" in val:
            return 0
        try:
            return int(float(re.sub(r"[^0-9]", "", val)))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def clean_bathrooms(value: Any) -> Optional[float]:
        """Convert bathroom count to float."""
        if pd.isna(value):
            return None
        try:
            return float(str(value).strip().replace("½", ".5").replace("½", ".5"))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def clean_property_type(value: Any) -> Optional[str]:
        """Standardize property type."""
        if pd.isna(value) or str(value).strip() == "":
            return None
        val = str(value).strip().lower()
        if any(x in val for x in ["single family", "single-family", "house"]):
            return "Single Family"
        elif any(x in val for x in ["condo", "condominium"]):
            return "Condo"
        elif any(x in val for x in ["townhouse", "town house"]):
            return "Townhouse"
        elif any(x in val for x in ["multi family", "multi-family", "duplex"]):
            return "Multi-Family"
        elif any(x in val for x in ["land", "lot", "acreage"]):
            return "Land"
        elif any(x in val for x in ["commercial"]):
            return "Commercial"
        return val.title()

    @staticmethod
    def clean_zip_code(value: Any) -> Optional[str]:
        """Validate and format ZIP code."""
        if pd.isna(value):
            return None
        val = str(value).strip()
        digits = re.sub(r"\D", "", val)
        if len(digits) == 5:
            return digits
        elif len(digits) == 9:
            return f"{digits[:5]}-{digits[5:]}"
        return val


class SurveyCleaner:
    """Cleaning functions for survey/feedback data."""

    @staticmethod
    def clean_rating(value: Any) -> Optional[int]:
        """Convert rating to integer (1-5 or 1-10 scale)."""
        if pd.isna(value):
            return None
        val = str(value).strip().lower()
        try:
            num = int(float(val))
            if 0 <= num <= 10:
                return num
            elif num > 10:
                return min(10, num)
        except (ValueError, TypeError):
            pass
        if any(x in val for x in ["strongly agree", "excellent", "very satisfied"]):
            return 5
        elif any(x in val for x in ["agree", "satisfied"]):
            return 4
        elif any(x in val for x in ["neutral", "neither"]):
            return 3
        elif any(x in val for x in ["disagree", "unsatisfied"]):
            return 2
        elif any(x in val for x in ["strongly disagree", "very unsatisfied"]):
            return 1
        return None

    @staticmethod
    def clean_NPS_score(value: Any) -> Optional[int]:
        """Validate NPS score (-100 to 100)."""
        if pd.isna(value):
            return None
        try:
            score = int(float(str(value).strip()))
            if -100 <= score <= 100:
                return score
        except (ValueError, TypeError):
            pass
        return None

    @staticmethod
    def clean_yes_no(value: Any) -> Optional[str]:
        """Standardize yes/no responses."""
        if pd.isna(value) or str(value).strip() == "":
            return None
        val = str(value).strip().lower()
        if val in ["yes", "y", "true", "1", "si", "yeah", "aye"]:
            return "Yes"
        elif val in ["no", "n", "false", "0", "nah", "nope"]:
            return "No"
        return val.title()

    @staticmethod
    def clean_satisfaction(value: Any) -> Optional[str]:
        """Standardize satisfaction levels."""
        if pd.isna(value) or str(value).strip() == "":
            return None
        val = str(value).strip().lower()
        if any(x in val for x in ["very satisfied", "extremely happy", "delighted"]):
            return "Very Satisfied"
        elif any(x in val for x in ["satisfied", "happy", "pleased"]):
            return "Satisfied"
        elif any(x in val for x in ["neutral", "neither"]):
            return "Neutral"
        elif any(x in val for x in ["unsatisfied", "dissatisfied", "unhappy"]):
            return "Unsatisfied"
        elif any(x in val for x in ["very unsatisfied", "very unhappy", "terrible"]):
            return "Very Unsatisfied"
        return val.title()


class CustomerCleaner:
    """Cleaning functions for customer/CRM data."""

    @staticmethod
    def clean_lead_source(value: Any) -> Optional[str]:
        """Standardize lead sources."""
        if pd.isna(value) or str(value).strip() == "":
            return None
        val = str(value).strip().lower()
        if any(x in val for x in ["google", "search", "organic"]):
            return "Organic Search"
        elif any(x in val for x in ["facebook", "fb", "social"]):
            return "Social Media"
        elif any(x in val for x in ["linkedin"]):
            return "LinkedIn"
        elif any(x in val for x in ["referral", "referred"]):
            return "Referral"
        elif any(x in val for x in ["email", "newsletter"]):
            return "Email Campaign"
        elif any(x in val for x in ["direct", "walk-in", "walkin"]):
            return "Direct"
        elif any(x in val for x in ["trade", "展会"]):
            return "Trade Show"
        return val.title()

    @staticmethod
    def clean_deal_value(value: Any) -> Optional[float]:
        """Convert deal value to numeric."""
        if pd.isna(value):
            return None
        val = str(value).strip()
        val = val.replace("$", "").replace(",", "").replace(" ", "")
        try:
            return float(val)
        except ValueError:
            return None

    @staticmethod
    def clean_stage(value: Any) -> Optional[str]:
        """Standardize deal stages."""
        if pd.isna(value) or str(value).strip() == "":
            return None
        val = str(value).strip().lower()
        if any(x in val for x in ["won", "closed won", "success"]):
            return "Closed Won"
        elif any(x in val for x in ["lost", "closed lost", "failed"]):
            return "Closed Lost"
        elif any(x in val for x in ["negotiation", "negotiating"]):
            return "Negotiation"
        elif any(x in val for x in ["proposal", "quote"]):
            return "Proposal"
        elif any(x in val for x in ["qualified", "meeting"]):
            return "Qualified"
        elif any(x in val for x in ["lead", "prospect"]):
            return "Lead"
        return val.title()

    @staticmethod
    def clean_industry(value: Any) -> Optional[str]:
        """Standardize industry names."""
        if pd.isna(value) or str(value).strip() == "":
            return None
        val = str(value).strip().lower()
        industries = {
            "tech": "Technology",
            "technology": "Technology",
            "software": "Technology",
            "healthcare": "Healthcare",
            "health": "Healthcare",
            "finance": "Finance",
            "financial": "Finance",
            "banking": "Finance",
            "retail": "Retail",
            "ecommerce": "E-commerce",
            "manufacturing": "Manufacturing",
            "education": "Education",
            "real estate": "Real Estate",
            "realestate": "Real Estate",
        }
        for key, standardized in industries.items():
            if key in val:
                return standardized
        return val.title()


def get_cleaner_for_domain(domain: str):
    """Get the appropriate cleaner class for a domain."""
    cleaners = {
        "healthcare": HealthcareCleaner,
        "hr": HRCleaner,
        "financial": FinancialCleaner,
        "ecommerce": EcommerceCleaner,
        "logistics": LogisticsCleaner,
        "inventory": InventoryCleaner,
        "iot": IoTCleaner,
        "realestate": RealEstateCleaner,
        "real estate": RealEstateCleaner,
        "survey": SurveyCleaner,
        "customer": CustomerCleaner,
        "crm": CustomerCleaner,
        "student": StudentCleaner,
        "education": StudentCleaner,
        "manufacturing": ManufacturingCleaner,
        "restaurant": RestaurantCleaner,
        "food": RestaurantCleaner,
        "sports": SportsCleaner,
    }
    return cleaners.get(domain.lower())


def apply_domain_cleaning(df: pd.DataFrame, domain: str) -> pd.DataFrame:
    """Apply domain-specific cleaning rules."""
    domain_cleaners = {
        "healthcare": {
            "icd_code": HealthcareCleaner.clean_icd_code,
            "ssn": HealthcareCleaner.clean_ssn,
            "npi": HealthcareCleaner.clean_npi,
            "medication": HealthcareCleaner.clean_medication,
            "blood_group": HealthcareCleaner.clean_blood_type,
            "dob": HealthcareCleaner.clean_dob,
        },
        "financial": {
            "amount": FinancialCleaner.clean_amount,
            "balance": FinancialCleaner.clean_amount,
            "price": FinancialCleaner.clean_currency,
            "cost": FinancialCleaner.clean_currency,
            "account_no": FinancialCleaner.clean_account_number,
            "iban": FinancialCleaner.clean_iban,
            "card_number": FinancialCleaner.clean_card_number,
            "txn_type": FinancialCleaner.clean_transaction_type,
        },
        "ecommerce": {
            "sku": EcommerceCleaner.clean_sku,
            "product_name": EcommerceCleaner.clean_product_name,
            "category": EcommerceCleaner.clean_category,
            "rating": EcommerceCleaner.clean_rating,
        },
        "hr": {
            "emp_id": HRCleaner.clean_employee_id,
            "department": HRCleaner.clean_department,
            "salary": HRCleaner.clean_salary,
            "performance": HRCleaner.clean_performance_rating,
        },
        "logistics": {
            "tracking_number": LogisticsCleaner.clean_tracking_number,
            "weight": LogisticsCleaner.clean_weight,
            "dimensions": LogisticsCleaner.clean_dimensions,
            "status": LogisticsCleaner.clean_shipping_status,
        },
        "inventory": {
            "sku": InventoryCleaner.clean_sku,
            "upc": InventoryCleaner.clean_upc,
            "quantity": InventoryCleaner.clean_quantity,
            "unit_price": InventoryCleaner.clean_unit_price,
            "stock_status": InventoryCleaner.clean_stock_status,
            "location": InventoryCleaner.clean_location,
        },
        "iot": {
            "sensor_value": IoTCleaner.clean_sensor_value,
            "reading": IoTCleaner.clean_sensor_value,
            "mac_address": IoTCleaner.clean_mac_address,
            "ip_address": IoTCleaner.clean_ip_address,
            "ip": IoTCleaner.clean_ip_address,
            "timestamp": IoTCleaner.clean_timestamp,
            "device_id": IoTCleaner.clean_device_id,
            "battery_level": IoTCleaner.clean_battery_level,
        },
        "realestate": {
            "property_address": RealEstateCleaner.clean_property_address,
            "address": RealEstateCleaner.clean_property_address,
            "price": RealEstateCleaner.clean_price,
            "amount": RealEstateCleaner.clean_price,
            "area": RealEstateCleaner.clean_area_sqft,
            "sqft": RealEstateCleaner.clean_area_sqft,
            "bedrooms": RealEstateCleaner.clean_bedrooms,
            "beds": RealEstateCleaner.clean_bedrooms,
            "bathrooms": RealEstateCleaner.clean_bathrooms,
            "baths": RealEstateCleaner.clean_bathrooms,
            "property_type": RealEstateCleaner.clean_property_type,
            "type": RealEstateCleaner.clean_property_type,
            "zip_code": RealEstateCleaner.clean_zip_code,
            "zipcode": RealEstateCleaner.clean_zip_code,
        },
        "survey": {
            "rating": SurveyCleaner.clean_rating,
            "nps_score": SurveyCleaner.clean_NPS_score,
            "nps": SurveyCleaner.clean_NPS_score,
            "yes_no": SurveyCleaner.clean_yes_no,
            "satisfaction": SurveyCleaner.clean_satisfaction,
        },
        "customer": {
            "lead_source": CustomerCleaner.clean_lead_source,
            "source": CustomerCleaner.clean_lead_source,
            "deal_value": CustomerCleaner.clean_deal_value,
            "value": CustomerCleaner.clean_deal_value,
            "stage": CustomerCleaner.clean_stage,
            "status": CustomerCleaner.clean_stage,
            "industry": CustomerCleaner.clean_industry,
        },
        "student": {
            "student_id": StudentCleaner.clean_student_id,
            "id": StudentCleaner.clean_student_id,
            "gpa": StudentCleaner.clean_gpa,
            "grade": StudentCleaner.clean_grade,
            "attendance": StudentCleaner.clean_attendance,
            "major": StudentCleaner.clean_major,
            "enrollment_status": StudentCleaner.clean_enrollment_status,
        },
        "education": {
            "student_id": StudentCleaner.clean_student_id,
            "gpa": StudentCleaner.clean_gpa,
            "grade": StudentCleaner.clean_grade,
            "attendance": StudentCleaner.clean_attendance,
        },
        "manufacturing": {
            "production_id": ManufacturingCleaner.clean_production_id,
            "batch_number": ManufacturingCleaner.clean_batch_number,
            "defect_rate": ManufacturingCleaner.clean_defect_rate,
            "quality_score": ManufacturingCleaner.clean_quality_score,
            "machine_id": ManufacturingCleaner.clean_machine_id,
        },
        "restaurant": {
            "order_id": RestaurantCleaner.clean_order_id,
            "order": RestaurantCleaner.clean_order_id,
            "rating": RestaurantCleaner.clean_rating,
            "tip": RestaurantCleaner.clean_tip,
            "total_bill": RestaurantCleaner.clean_total_bill,
            "payment_type": RestaurantCleaner.clean_payment_type,
        },
        "sports": {
            "player_id": SportsCleaner.clean_player_id,
            "id": SportsCleaner.clean_player_id,
            "jersey_number": SportsCleaner.clean_jersey_number,
            "score": SportsCleaner.clean_score,
            "height": SportsCleaner.clean_height,
            "weight": SportsCleaner.clean_weight,
            "position": SportsCleaner.clean_position,
        },
    }

    domain_key = domain.lower()
    if domain_key not in domain_cleaners:
        for key in domain_cleaners:
            if key in domain_key or domain_key in key:
                domain_key = key
                break
        else:
            return df

    column_cleaner_map = domain_cleaners[domain_key]

    for col, func in column_cleaner_map.items():
        if col in df.columns:
            df[col] = df[col].apply(func)

    return df


class StudentCleaner:
    """Cleaning functions for student/education data."""

    @staticmethod
    def clean_student_id(value: Any) -> Optional[str]:
        """Standardize student ID format."""
        if pd.isna(value) or str(value).strip() == "":
            return None
        val = str(value).strip().upper()
        val = re.sub(r"[^A-Z0-9-]", "", val)
        return val

    @staticmethod
    def clean_gpa(value: Any) -> Optional[float]:
        """Validate and normalize GPA (0-4.0 or 0-100 scale)."""
        if pd.isna(value):
            return None
        val = str(value).strip()
        try:
            gpa = float(val)
            if gpa > 10:
                gpa = gpa / 25
            return max(0, min(4.0, gpa))
        except ValueError:
            return None

    @staticmethod
    def clean_grade(value: Any) -> Optional[str]:
        """Standardize grade values."""
        if pd.isna(value) or str(value).strip() == "":
            return None
        val = str(value).strip().upper()
        grade_map = {
            "A+": "A",
            "A": "A",
            "A-": "A",
            "B+": "B",
            "B": "B",
            "B-": "B",
            "C+": "C",
            "C": "C",
            "C-": "C",
            "D+": "D",
            "D": "D",
            "D-": "D",
            "F": "F",
            "FAIL": "F",
            "PASS": "P",
        }
        return grade_map.get(val, val)

    @staticmethod
    def clean_attendance(value: Any) -> Optional[float]:
        """Convert attendance to percentage."""
        if pd.isna(value):
            return None
        val = str(value).strip().replace("%", "")
        try:
            att = float(val)
            if att > 1:
                att = att / 100
            return max(0, min(100, att * 100))
        except ValueError:
            return None

    @staticmethod
    def clean_major(value: Any) -> Optional[str]:
        """Standardize major/department names."""
        if pd.isna(value) or str(value).strip() == "":
            return None
        val = str(value).strip().title()
        major_map = {
            "Cs": "Computer Science",
            "Comp Sci": "Computer Science",
            "Csci": "Computer Science",
            "Ee": "Electrical Engineering",
            "Mech Eng": "Mechanical Engineering",
            "Mkt": "Marketing",
            "Bio": "Biology",
            "Poli Sci": "Political Science",
            "Psych": "Psychology",
        }
        for abbr, full in major_map.items():
            if abbr.lower() in val.lower():
                return full
        return val

    @staticmethod
    def clean_enrollment_status(value: Any) -> Optional[str]:
        """Standardize enrollment status."""
        if pd.isna(value) or str(value).strip() == "":
            return None
        val = str(value).strip().lower()
        if any(
            x in val for x in ["active", "enrolled", "current", "full-time", "fulltime"]
        ):
            return "Active"
        elif any(x in val for x in ["graduated", "complete", "graduation"]):
            return "Graduated"
        elif any(x in val for x in ["withdrawn", "dropped", "left", "quit"]):
            return "Withdrawn"
        elif any(x in val for x in ["suspended", "expelled", "dismissed"]):
            return "Suspended"
        elif any(x in val for x in ["on hold", "sabbatical", "leave"]):
            return "On Leave"
        return val.title()


class ManufacturingCleaner:
    """Cleaning functions for manufacturing data."""

    @staticmethod
    def clean_production_id(value: Any) -> Optional[str]:
        """Standardize production ID format."""
        if pd.isna(value) or str(value).strip() == "":
            return None
        val = str(value).strip().upper()
        val = re.sub(r"[^A-Z0-9-]", "", val)
        return val

    @staticmethod
    def clean_batch_number(value: Any) -> Optional[str]:
        """Standardize batch number format."""
        if pd.isna(value) or str(value).strip() == "":
            return None
        val = str(value).strip().upper()
        val = re.sub(r"[^A-Z0-9-]", "", val)
        return val

    @staticmethod
    def clean_defect_rate(value: Any) -> Optional[float]:
        """Convert defect rate to percentage."""
        if pd.isna(value):
            return None
        val = str(value).strip().replace("%", "")
        try:
            rate = float(val)
            if rate <= 1:
                rate = rate * 100
            return max(0, min(100, rate))
        except ValueError:
            return None

    @staticmethod
    def clean_quality_score(value: Any) -> Optional[float]:
        """Validate quality score (0-100 scale)."""
        if pd.isna(value):
            return None
        val = str(value).strip().replace("%", "")
        try:
            score = float(val)
            if score > 10:
                score = score / 10
            return max(0, min(100, score))
        except ValueError:
            return None

    @staticmethod
    def clean_machine_id(value: Any) -> Optional[str]:
        """Standardize machine ID format."""
        if pd.isna(value) or str(value).strip() == "":
            return None
        val = str(value).strip().upper()
        val = re.sub(r"[^A-Z0-9]", "", val)
        return val


class RestaurantCleaner:
    """Cleaning functions for restaurant/hospitality data."""

    @staticmethod
    def clean_order_id(value: Any) -> Optional[str]:
        """Standardize order ID format."""
        if pd.isna(value) or str(value).strip() == "":
            return None
        val = str(value).strip().upper()
        val = re.sub(r"[^A-Z0-9-]", "", val)
        return val

    @staticmethod
    def clean_rating(value: Any) -> Optional[float]:
        """Convert rating to 0-5 scale."""
        if pd.isna(value):
            return None
        val = str(value).strip()
        try:
            rating = float(val)
            if rating > 5:
                rating = rating / 20
            return max(0, min(5, rating))
        except ValueError:
            return None

    @staticmethod
    def clean_tip(value: Any) -> Optional[float]:
        """Convert tip to numeric."""
        if pd.isna(value):
            return None
        val = str(value).strip().replace("$", "").replace(",", "")
        try:
            return float(val)
        except ValueError:
            return None

    @staticmethod
    def clean_total_bill(value: Any) -> Optional[float]:
        """Convert total bill to numeric."""
        if pd.isna(value):
            return None
        val = str(value).strip()
        val = val.replace("$", "").replace(",", "").replace(" ", "")
        try:
            return float(val)
        except ValueError:
            return None

    @staticmethod
    def clean_payment_type(value: Any) -> Optional[str]:
        """Standardize payment type."""
        if pd.isna(value) or str(value).strip() == "":
            return None
        val = str(value).strip().lower()
        if any(x in val for x in ["cash", "bill"]):
            return "Cash"
        elif any(x in val for x in ["credit", "card"]):
            return "Credit Card"
        elif any(x in val for x in ["debit"]):
            return "Debit Card"
        elif any(x in val for x in ["mobile", "apple pay", "google pay"]):
            return "Mobile Payment"
        return val.title()


class SportsCleaner:
    """Cleaning functions for sports data."""

    @staticmethod
    def clean_player_id(value: Any) -> Optional[str]:
        """Standardize player ID format."""
        if pd.isna(value) or str(value).strip() == "":
            return None
        val = str(value).strip().upper()
        val = re.sub(r"[^A-Z0-9-]", "", val)
        return val

    @staticmethod
    def clean_jersey_number(value: Any) -> Optional[int]:
        """Validate jersey number (typically 0-99)."""
        if pd.isna(value):
            return None
        try:
            num = int(float(str(value).strip()))
            if 0 <= num <= 99:
                return num
            return num % 100
        except (ValueError, TypeError):
            return None

    @staticmethod
    def clean_score(value: Any) -> Optional[int]:
        """Convert score to integer."""
        if pd.isna(value):
            return None
        try:
            return int(float(str(value).strip()))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def clean_height(value: Any) -> Optional[float]:
        """Convert height to inches."""
        if pd.isna(value):
            return None
        val = str(value).strip().lower()
        try:
            if "'" in val or '"' in val or "ft" in val:
                import re as re_module

                match = re_module.search(r"(\d+)\s*['\"]?\s*(\d+)?", val)
                if match:
                    feet = int(match.group(1))
                    inches = int(match.group(2)) if match.group(2) else 0
                    return feet * 12 + inches
            elif "cm" in val or "centimeter" in val:
                num = float(re_module.sub(r"[^0-9.]", "", val))
                return num / 2.54
            else:
                return float(val)
        except:
            pass
        return None

    @staticmethod
    def clean_weight(value: Any) -> Optional[float]:
        """Convert weight to pounds."""
        if pd.isna(value):
            return None
        val = str(value).strip().lower()
        try:
            import re as re_module

            num = float(re_module.sub(r"[^0-9.]", "", val))
            if "kg" in val or "kilogram" in val:
                return num * 2.20462
            elif "stone" in val:
                return num * 14
            return num
        except:
            return None

    @staticmethod
    def clean_position(value: Any) -> Optional[str]:
        """Standardize position names."""
        if pd.isna(value) or str(value).strip() == "":
            return None
        val = str(value).strip().upper()
        positions = {
            "PG": "Point Guard",
            "SG": "Shooting Guard",
            "SF": "Small Forward",
            "PF": "Power Forward",
            "C": "Center",
            "G": "Guard",
            "F": "Forward",
            "QB": "Quarterback",
            "RB": "Running Back",
            "WR": "Wide Receiver",
            "TE": "Tight End",
            "OL": "Offensive Line",
            "DL": "Defensive Line",
            "LB": "Linebacker",
            "CB": "Cornerback",
            "S": "Safety",
            "GK": "Goalkeeper",
            "DF": "Defender",
            "MF": "Midfielder",
            "FW": "Forward",
            "ST": "Striker",
            "LW": "Left Wing",
            "RW": "Right Wing",
        }
        return positions.get(val, val)
