"""Pydantic data contracts mirroring the LATAM Bank data dictionary.

Only the tables needed for the Account/Payment Inquiries workflow are modeled:
customers, products, branches, transactions, daily_exchange_rates.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class Customer(BaseModel):
    customer_id: str
    document_number: str
    document_type: str
    first_name: str
    last_name: str
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    email: Optional[str] = None
    mobile_phone: Optional[str] = None
    landline_phone: Optional[str] = None
    address: Optional[str] = None
    city: str
    state: str
    country: str
    postal_code: Optional[str] = None
    detected_accent: Optional[str] = None
    segment: str
    credit_score: Optional[int] = None
    estimated_monthly_income: Optional[Decimal] = None
    occupation: Optional[str] = None
    marital_status: Optional[str] = None
    education_level: Optional[str] = None
    registration_date: datetime
    registration_branch_id: str
    customer_status: str
    last_updated: datetime
    accepts_marketing: Optional[bool] = None

    @field_validator("date_of_birth", "registration_date", "last_updated", mode="before")
    @classmethod
    def _empty_to_none(cls, v):
        if v == "" or v is None:
            return None
        return v


class Product(BaseModel):
    product_id: str
    customer_id: str
    product_type: str
    product_number: str
    currency: str
    current_balance: Decimal
    credit_limit: Optional[Decimal] = None
    interest_rate: Optional[Decimal] = None
    opening_date: date
    expiration_date: Optional[date] = None
    opening_branch_id: str
    product_status: str
    opening_channel: str
    has_linked_app: Optional[bool] = None
    days_past_due: Optional[int] = None
    last_transaction_date: Optional[datetime] = None
    last_updated: datetime


class Branch(BaseModel):
    branch_id: str
    branch_code: str
    branch_name: str
    branch_type: str
    address: str
    city: str
    state: str
    country: str
    postal_code: Optional[str] = None
    geographic_zone: str
    phone: str
    email: Optional[str] = None
    branch_status: str


class Transaction(BaseModel):
    transaction_id: str
    transaction_date: datetime
    process_date: date
    product_id: str
    customer_id: str
    transaction_type: str
    transaction_category: Optional[str] = None
    amount: Decimal
    currency: str
    amount_usd: Optional[Decimal] = None
    channel: str
    branch_id: Optional[str] = None
    merchant_name: Optional[str] = None
    merchant_category: Optional[str] = None
    transaction_country: str
    transaction_city: Optional[str] = None
    transaction_status: str
    response_code: Optional[str] = None
    is_fraud: bool = False
    fraud_score: Optional[Decimal] = None


class ExchangeRate(BaseModel):
    date: date
    source_currency: str
    target_currency: str
    exchange_rate: Decimal
    buy_rate: Optional[Decimal] = None
    sell_rate: Optional[Decimal] = None
    source: Optional[str] = None


TABLE_CONTRACTS = {
    "customers": Customer,
    "products": Product,
    "branches": Branch,
    "transactions": Transaction,
    "daily_exchange_rates": ExchangeRate,
}

# Primary keys used for idempotent upserts during ingestion.
PRIMARY_KEYS = {
    "customers": ["customer_id"],
    "products": ["product_id"],
    "branches": ["branch_id"],
    "transactions": ["transaction_id"],
    "daily_exchange_rates": ["date", "source_currency", "target_currency"],
}

# Non-nullable columns per the data dictionary, used for quality checks.
NOT_NULL_COLUMNS = {
    "customers": [
        "customer_id", "document_number", "document_type", "first_name",
        "last_name", "date_of_birth", "city", "state", "country", "segment",
        "registration_date", "registration_branch_id", "customer_status", "last_updated",
    ],
    "products": [
        "product_id", "customer_id", "product_type", "product_number", "currency",
        "current_balance", "opening_date", "opening_branch_id", "product_status",
        "opening_channel", "last_updated",
    ],
    "branches": [
        "branch_id", "branch_code", "branch_name", "branch_type", "address",
        "city", "state", "country", "geographic_zone", "phone", "branch_status",
    ],
    "transactions": [
        "transaction_id", "transaction_date", "process_date", "product_id",
        "customer_id", "transaction_type", "amount", "currency", "channel",
        "transaction_country", "transaction_status", "is_fraud",
    ],
    "daily_exchange_rates": ["date", "source_currency", "target_currency", "exchange_rate"],
}

# Foreign-key relationships used for orphan-rate quality checks.
FOREIGN_KEYS = {
    "products": [("customer_id", "customers", "customer_id"), ("opening_branch_id", "branches", "branch_id")],
    "transactions": [("customer_id", "customers", "customer_id"), ("product_id", "products", "product_id")],
    "customers": [("registration_branch_id", "branches", "branch_id")],
}
