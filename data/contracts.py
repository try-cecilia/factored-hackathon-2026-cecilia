"""Data contracts for the LATAM Bank dataset, executed by data/pipeline.py.

Four layers, all enforced at ingestion (see data/quality.py):
1. COLUMN_TYPES   - the data dictionary's declared types. Raw CSVs are read
                    untyped, then TRY_CAST to these; a non-null raw value that
                    fails its cast is a contract violation (quarantined).
2. NOT_NULL / PK  - dictionary NOT NULL constraints and primary keys
                    (duplicates are measured on the raw batch, before dedup).
3. DOMAIN_RULES   - enums/ranges per table. `error` rules quarantine the row;
                    `warn` rules are measured and reported, never block.
4. CROSS_TABLE    - consistency checks that need other tables (FK orphans,
                    txn/product ownership agreement, currency coherence).

The pydantic models are an independent row-level validator run on a sample
of every load, so the SQL contract and the Python contract can't silently
drift apart. Enum values reflect what the data actually contains: e.g. the
dictionary lists product types in English, but the data ships them in
Spanish ("Tarjeta Crédito") — that doc/data mismatch is recorded in
docs/data_quality.md rather than "fixed" by rewriting the source.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict

CONTRACT_VERSION = "2.1.0"

CREDIT_PRODUCT_TYPES = ("Tarjeta Crédito", "Préstamo Personal", "Préstamo Hipotecario")
PRODUCT_TYPES = (
    "Cuenta Ahorro", "Cuenta Corriente", "Tarjeta Débito", "Tarjeta Crédito",
    "Préstamo Personal", "Préstamo Hipotecario", "Inversión", "Seguro",
)
CURRENCIES = ("MXN", "COP", "ARS", "USD")
COUNTRY_LOCAL_CURRENCY = {"México": "MXN", "Colombia": "COP", "Argentina": "ARS"}

COLUMN_TYPES: dict[str, dict[str, str]] = {
    "customers": {
        "customer_id": "VARCHAR", "document_number": "VARCHAR", "document_type": "VARCHAR",
        "first_name": "VARCHAR", "last_name": "VARCHAR", "date_of_birth": "DATE", "gender": "VARCHAR",
        "email": "VARCHAR", "mobile_phone": "VARCHAR", "landline_phone": "VARCHAR", "address": "VARCHAR",
        "city": "VARCHAR", "state": "VARCHAR", "country": "VARCHAR", "postal_code": "VARCHAR",
        "detected_accent": "VARCHAR", "segment": "VARCHAR", "credit_score": "INTEGER",
        "estimated_monthly_income": "DECIMAL(12,2)", "occupation": "VARCHAR", "marital_status": "VARCHAR",
        "education_level": "VARCHAR", "registration_date": "TIMESTAMP", "registration_branch_id": "VARCHAR",
        "customer_status": "VARCHAR", "last_updated": "TIMESTAMP", "accepts_marketing": "BOOLEAN",
    },
    "products": {
        "product_id": "VARCHAR", "customer_id": "VARCHAR", "product_type": "VARCHAR",
        "product_number": "VARCHAR", "currency": "VARCHAR", "current_balance": "DECIMAL(15,2)",
        "credit_limit": "DECIMAL(15,2)", "interest_rate": "DECIMAL(5,2)", "opening_date": "DATE",
        "expiration_date": "DATE", "opening_branch_id": "VARCHAR", "product_status": "VARCHAR",
        "opening_channel": "VARCHAR", "has_linked_app": "BOOLEAN", "days_past_due": "INTEGER",
        "last_transaction_date": "TIMESTAMP", "last_updated": "TIMESTAMP",
    },
    "branches": {
        "branch_id": "VARCHAR", "branch_code": "VARCHAR", "branch_name": "VARCHAR", "branch_type": "VARCHAR",
        "address": "VARCHAR", "city": "VARCHAR", "state": "VARCHAR", "country": "VARCHAR",
        "postal_code": "VARCHAR", "geographic_zone": "VARCHAR", "phone": "VARCHAR", "email": "VARCHAR",
        "opening_time": "TIME", "closing_time": "TIME", "has_atms": "BOOLEAN", "atm_count": "INTEGER",
        "has_teller_windows": "BOOLEAN", "teller_window_count": "INTEGER", "latitude": "DECIMAL(10,7)",
        "longitude": "DECIMAL(10,7)", "branch_opening_date": "DATE", "branch_status": "VARCHAR",
    },
    "daily_exchange_rates": {
        "date": "DATE", "source_currency": "VARCHAR", "target_currency": "VARCHAR",
        "exchange_rate": "DECIMAL(12,6)", "buy_rate": "DECIMAL(12,6)", "sell_rate": "DECIMAL(12,6)",
        "source": "VARCHAR",
    },
    "transactions": {
        "transaction_id": "VARCHAR", "transaction_date": "TIMESTAMP", "process_date": "DATE",
        "product_id": "VARCHAR", "customer_id": "VARCHAR", "transaction_type": "VARCHAR",
        "transaction_category": "VARCHAR", "amount": "DECIMAL(15,2)", "currency": "VARCHAR",
        "amount_usd": "DECIMAL(15,2)", "channel": "VARCHAR", "branch_id": "VARCHAR",
        "merchant_name": "VARCHAR", "merchant_category": "VARCHAR", "transaction_country": "VARCHAR",
        "transaction_city": "VARCHAR", "transaction_status": "VARCHAR", "response_code": "VARCHAR",
        "is_fraud": "BOOLEAN", "fraud_score": "DECIMAL(5,2)", "latitude": "DECIMAL(10,7)",
        "longitude": "DECIMAL(10,7)",
    },
    "call_center_interactions": {
        "interaction_id": "VARCHAR", "interaction_date": "TIMESTAMP", "process_date": "DATE",
        "customer_id": "VARCHAR", "agent_id": "VARCHAR", "interaction_type": "VARCHAR", "channel": "VARCHAR",
        "contact_reason": "VARCHAR", "reason_category": "VARCHAR", "duration_seconds": "INTEGER",
        "wait_time_seconds": "INTEGER", "was_resolved": "BOOLEAN", "requires_followup": "BOOLEAN",
        "detected_sentiment": "VARCHAR", "sentiment_score": "DECIMAL(3,2)",
        "customer_detected_accent": "VARCHAR", "agent_used_accent": "VARCHAR", "was_escalated": "BOOLEAN",
        "mentioned_products": "VARCHAR", "has_transcript": "BOOLEAN", "has_recording": "BOOLEAN",
    },
    "call_transcripts": {
        "transcript_id": "VARCHAR", "interaction_id": "VARCHAR", "process_date": "DATE",
        "customer_id": "VARCHAR", "agent_id": "VARCHAR", "full_text": "VARCHAR", "customer_text": "VARCHAR",
        "agent_text": "VARCHAR", "detected_language": "VARCHAR", "detected_accent": "VARCHAR",
        "accent_confidence": "DECIMAL(3,2)", "detected_keywords": "VARCHAR", "mentioned_entities": "VARCHAR",
        "detected_intents": "VARCHAR", "main_topics": "VARCHAR", "transcription_model": "VARCHAR",
        "audio_quality": "VARCHAR", "duration_seconds": "INTEGER",
    },
    "satisfaction_surveys": {
        "survey_id": "VARCHAR", "survey_date": "TIMESTAMP", "process_date": "DATE",
        "interaction_id": "VARCHAR", "customer_id": "VARCHAR", "agent_id": "VARCHAR",
        "survey_type": "VARCHAR", "send_channel": "VARCHAR", "main_score": "INTEGER",
        "nps_category": "VARCHAR", "question_1_text": "VARCHAR", "question_1_response": "INTEGER",
        "question_2_text": "VARCHAR", "question_2_response": "INTEGER", "question_3_text": "VARCHAR",
        "question_3_response": "INTEGER", "open_comments": "VARCHAR", "comment_sentiment": "VARCHAR",
        "response_time_hours": "DECIMAL(8,2)", "campaign_response_rate": "DECIMAL(5,2)",
    },
    "complaints": {
        "complaint_id": "VARCHAR", "creation_date": "TIMESTAMP", "process_date": "DATE",
        "customer_id": "VARCHAR", "case_type": "VARCHAR", "category": "VARCHAR",
        "subcategory": "VARCHAR", "reception_channel": "VARCHAR", "affected_product_id": "VARCHAR",
        "related_branch_id": "VARCHAR", "origin_interaction_id": "VARCHAR", "description": "VARCHAR",
        "claimed_amount": "DECIMAL(15,2)", "currency": "VARCHAR", "priority": "VARCHAR",
        "status": "VARCHAR", "assigned_agent_id": "VARCHAR", "assignment_date": "TIMESTAMP",
        "first_response_date": "TIMESTAMP", "resolution_date": "TIMESTAMP", "closing_date": "TIMESTAMP",
        "sla_breached": "BOOLEAN", "resolution_days": "INTEGER", "resolution": "VARCHAR",
        "compensation_granted": "DECIMAL(15,2)", "resolution_satisfaction": "INTEGER",
        "is_repeat_complainer": "BOOLEAN",
    },
}

PRIMARY_KEYS = {
    "customers": ["customer_id"],
    "products": ["product_id"],
    "branches": ["branch_id"],
    "transactions": ["transaction_id"],
    "daily_exchange_rates": ["date", "source_currency", "target_currency"],
    "call_center_interactions": ["interaction_id"],
    "call_transcripts": ["transcript_id"],
    "satisfaction_surveys": ["survey_id"],
    "complaints": ["complaint_id"],
}

# Column that decides which duplicate survives dedup (latest wins). Tables
# without one fall back to the later source file (a later partition = a
# late-arriving correction).
DEDUP_ORDER = {"customers": "last_updated", "products": "last_updated"}

NOT_NULL_COLUMNS = {
    "customers": [
        "customer_id", "document_number", "document_type", "first_name", "last_name", "date_of_birth",
        "city", "state", "country", "segment", "registration_date", "registration_branch_id",
        "customer_status", "last_updated", "accepts_marketing",
    ],
    "products": [
        "product_id", "customer_id", "product_type", "product_number", "currency", "current_balance",
        "opening_date", "opening_branch_id", "product_status", "opening_channel", "has_linked_app",
        "last_updated",
    ],
    "branches": [
        "branch_id", "branch_code", "branch_name", "branch_type", "address", "city", "state", "country",
        "geographic_zone", "phone", "opening_time", "closing_time", "has_atms", "has_teller_windows",
        "branch_opening_date", "branch_status",
    ],
    "transactions": [
        "transaction_id", "transaction_date", "process_date", "product_id", "customer_id",
        "transaction_type", "amount", "currency", "channel", "transaction_country",
        "transaction_status", "is_fraud",
    ],
    "daily_exchange_rates": ["date", "source_currency", "target_currency", "exchange_rate"],
    "call_center_interactions": [
        "interaction_id", "interaction_date", "process_date", "customer_id", "interaction_type",
        "channel", "contact_reason", "reason_category", "requires_followup", "was_escalated",
        "has_transcript", "has_recording",
    ],
    "call_transcripts": [
        "transcript_id", "interaction_id", "process_date", "customer_id", "agent_id", "full_text",
        "detected_language", "transcription_model",
    ],
    "satisfaction_surveys": [
        "survey_id", "survey_date", "process_date", "customer_id", "survey_type", "send_channel", "main_score",
    ],
    "complaints": [
        "complaint_id", "creation_date", "process_date", "customer_id", "case_type", "category",
        "reception_channel", "description", "priority", "status", "sla_breached", "is_repeat_complainer",
    ],
}


# The five categories the dictionary lists (p. 9); the data also carries "Retención" (20,578 rows in the full run).
DICTIONARY_REASON_CATEGORIES = ["Transaccional", "Producto", "Queja", "Técnico", "Comercial"]


def _in(col: str, values) -> str:
    quoted = ", ".join("'" + v.replace("'", "''") + "'" for v in values)
    return f"{col} IN ({quoted})"


# (rule_name, SQL predicate that must be TRUE for a valid row, severity)
DOMAIN_RULES: dict[str, list[tuple[str, str, str]]] = {
    "customers": [
        ("segment_enum", _in("segment", ["Premium", "Plus", "Basic", "Student"]), "error"),
        ("status_enum", _in("customer_status", ["Active", "Inactive", "Suspended", "Closed"]), "error"),
        ("country_enum", _in("country", list(COUNTRY_LOCAL_CURRENCY)), "error"),
        ("credit_score_range", "credit_score IS NULL OR credit_score BETWEEN 300 AND 850", "error"),
        ("dob_not_future", "date_of_birth <= CAST(registration_date AS DATE)", "warn"),
    ],
    "products": [
        ("type_enum", _in("product_type", PRODUCT_TYPES), "error"),
        ("currency_enum", _in("currency", CURRENCIES), "error"),
        ("status_enum", _in("product_status", ["Active", "Blocked", "Closed", "Suspended"]), "error"),
        ("dpd_non_negative", "days_past_due IS NULL OR days_past_due >= 0", "error"),
        ("credit_fields_present",
         f"NOT {_in('product_type', CREDIT_PRODUCT_TYPES)} OR (credit_limit IS NOT NULL AND days_past_due IS NOT NULL)",
         "warn"),
        ("closed_has_zero_balance", "product_status <> 'Closed' OR current_balance = 0", "warn"),
    ],
    "branches": [
        ("status_enum", _in("branch_status", ["Active", "Temporarily Closed", "Closed"]), "warn"),
    ],
    "daily_exchange_rates": [
        ("rate_positive", "exchange_rate > 0", "error"),
        ("currency_enum", f"{_in('source_currency', CURRENCIES)} AND {_in('target_currency', CURRENCIES)}", "error"),
        ("distinct_pair", "source_currency <> target_currency", "error"),
    ],
    "transactions": [
        ("type_enum", _in("transaction_type", ["Deposit", "Withdrawal", "Transfer", "Payment", "Purchase", "Adjustment"]), "error"),
        ("status_enum", _in("transaction_status", ["Approved", "Declined", "Pending", "Reversed"]), "error"),
        ("channel_enum", _in("channel", ["ATM", "Branch", "Web", "App", "POS", "Transfer"]), "error"),
        ("currency_enum", _in("currency", CURRENCIES), "error"),
        ("amount_positive", "amount > 0", "error"),
        ("fraud_score_range", "fraud_score IS NULL OR fraud_score BETWEEN 0 AND 100", "error"),
        ("usd_amount_present", "amount_usd IS NOT NULL", "warn"),
        ("usd_amount_matches_for_usd", "currency <> 'USD' OR amount_usd IS NULL OR abs(amount_usd - amount) <= 0.01", "warn"),
        # A transaction processed more than a day after it happened is a late arrival.
        ("not_late_arrival", "process_date <= CAST(transaction_date AS DATE) + 1", "warn"),
    ],
    "call_center_interactions": [
        ("duration_non_negative", "duration_seconds IS NULL OR duration_seconds >= 0", "error"),
        ("wait_non_negative", "wait_time_seconds IS NULL OR wait_time_seconds >= 0", "error"),
        ("reason_equals_category", "contact_reason = reason_category", "warn"),
        ("reason_category_in_dictionary", _in("reason_category", DICTIONARY_REASON_CATEGORIES), "warn"),
    ],
    "call_transcripts": [
        ("agent_text_rendered", "agent_text IS NULL OR agent_text NOT LIKE '%{%}%'", "warn"),
        ("dictionary_not_null:duration_seconds", "duration_seconds IS NOT NULL", "warn"),
    ],
    "satisfaction_surveys": [
        ("csat_range", "survey_type <> 'CSAT' OR main_score BETWEEN 1 AND 5", "warn"),
        ("nps_range", "survey_type <> 'NPS' OR main_score BETWEEN 0 AND 10", "warn"),
    ],
    "complaints": [
        ("case_type_enum", _in("case_type", ["Complaint", "Claim", "Request", "Suggestion"]), "error"),
        ("channel_enum", _in("reception_channel", ["Call Center", "Email", "Web", "App", "Branch", "Regulator"]), "error"),
        ("currency_enum", f"currency IS NULL OR {_in('currency', CURRENCIES)}", "error"),
        ("priority_enum", _in("priority", ["Low", "Medium", "High", "Critical"]), "error"),
        ("status_enum", _in("status", ["Open", "In Process", "Escalated", "Resolved", "Closed", "Rejected"]), "error"),
        ("resolution_days_non_negative", "resolution_days IS NULL OR resolution_days >= 0", "error"),
        ("resolution_satisfaction_range",
         "resolution_satisfaction IS NULL OR resolution_satisfaction BETWEEN 1 AND 5", "error"),
        ("claimed_amount_has_currency", "claimed_amount IS NULL OR currency IS NOT NULL", "warn"),
        ("resolved_has_evidence",
         "status NOT IN ('Resolved', 'Closed') OR (resolution_date IS NOT NULL AND resolution IS NOT NULL)", "warn"),
    ],
}

# Places where the delivered data contradicts the dictionary and we chose a
# documented deviation instead of quarantining. Each one is still measured
# (as a warn rule) on every load, so it can't silently get worse.
CONTRACT_DEVIATIONS = [
    {"table": "call_transcripts", "column": "duration_seconds", "dictionary": "INTEGER NOT NULL",
     "observed": "14.0% null (24,029 of 171,321 in the full run)",
     "decision": "warn rule instead of quarantine; analysis-only table, column unused"},
    {"table": "call_center_interactions", "column": "reason_category", "dictionary": "5 categories (p. 9)",
     "observed": "6th category \"Retención\" (20,578 of 686,296 in the full run)",
     "decision": "warn rule instead of quarantine; kept as delivered, never translated or remapped"},
]

# Excess rows over a key the dictionary declares UNIQUE (beyond the primary key), measured on the whole table.
def _unique(table: str, col: str) -> str:
    return (f"SELECT coalesce(sum(n - 1), 0), (SELECT count(*) FROM {table}) FROM "
            f"(SELECT count(*) AS n FROM {table} WHERE {col} IS NOT NULL GROUP BY {col}) WHERE n > 1")


# A dimension row "updated" after the data's as-of date (the last processed day of transactions). Dedup keeps the
# latest `last_updated`, so a row stamped in the future would win over any later, real correction.
def _updated_after_as_of(table: str) -> str:
    return (f"SELECT count(*) FILTER (WHERE CAST(last_updated AS DATE) > (SELECT max(process_date) FROM transactions)), "
            f"count(*) FROM {table}")


# (check_name, SQL returning (failed_rows, total_rows)) run after load, when referenced tables exist.
# The unique-key, chronology and as-of checks come from Matías Enrique's audit of the dataset (2026-09-28).
CROSS_TABLE_CHECKS: dict[str, list[tuple[str, list[str], str]]] = {
    "branches": [
        ("branch_code_unique", [], _unique("branches", "branch_code")),
    ],
    "products": [
        ("fk_customer", ["customers"],
         "SELECT count(*) FILTER (WHERE c.customer_id IS NULL), count(*) FROM products p LEFT JOIN customers c USING (customer_id)"),
        ("currency_local_or_usd", ["customers"],
         "SELECT count(*) FILTER (WHERE NOT (p.currency = 'USD' OR p.currency = CASE c.country "
         "WHEN 'México' THEN 'MXN' WHEN 'Colombia' THEN 'COP' WHEN 'Argentina' THEN 'ARS' END)), count(*) "
         "FROM products p JOIN customers c USING (customer_id)"),
        # Only the last 4 digits are ever shown and ownership is checked by product_id, so a repeated number
        # misleads nobody here; it would, if a customer were identified by product number.
        ("product_number_unique", [], _unique("products", "product_number")),
    ],
    "transactions": [
        ("fk_product", ["products"],
         "SELECT count(*) FILTER (WHERE p.product_id IS NULL), count(*) FROM transactions t LEFT JOIN products p USING (product_id)"),
        # The tool layer filters transactions by customer_id; if a transaction's
        # customer disagreed with its product's owner, answers would diverge.
        ("customer_owns_product", ["products"],
         "SELECT count(*) FILTER (WHERE p.customer_id <> t.customer_id), count(*) FROM transactions t JOIN products p USING (product_id)"),
        # A movement dated before its product was opened, or before its customer registered, is recorded as given:
        # the answers show it with its date, and these checks count it.
        ("tx_not_before_product_opening", ["products"],
         "SELECT count(*) FILTER (WHERE CAST(t.transaction_date AS DATE) < p.opening_date), count(*) "
         "FROM transactions t JOIN products p USING (product_id)"),
        ("tx_not_before_customer_registration", ["customers"],
         "SELECT count(*) FILTER (WHERE CAST(t.transaction_date AS DATE) < CAST(c.registration_date AS DATE)), count(*) "
         "FROM transactions t JOIN customers c USING (customer_id)"),
        # Here, not under customers or products: the as-of date exists once transactions are loaded.
        ("products_not_updated_after_as_of", ["products"], _updated_after_as_of("products")),
        ("customers_not_updated_after_as_of", ["customers"], _updated_after_as_of("customers")),
    ],
    "customers": [
        ("fk_registration_branch", ["branches"],
         "SELECT count(*) FILTER (WHERE b.branch_id IS NULL), count(*) FROM customers c LEFT JOIN branches b ON b.branch_id = c.registration_branch_id"),
        ("document_number_unique", [], _unique("customers", "document_number")),
    ],
    "call_center_interactions": [
        ("contact_not_before_registration", ["customers"],
         "SELECT count(*) FILTER (WHERE CAST(i.interaction_date AS DATE) < CAST(c.registration_date AS DATE)), count(*) "
         "FROM call_center_interactions i JOIN customers c USING (customer_id)"),
    ],
    "complaints": [
        ("fk_customer", ["customers"],
         "SELECT count(*) FILTER (WHERE u.customer_id IS NULL), count(*) "
         "FROM complaints c LEFT JOIN customers u USING (customer_id)"),
        # Optional FKs evaluate only non-null references. Their coverage is also
        # reported by each column's null-rate check.
        ("fk_affected_product", ["products"],
         "SELECT count(*) FILTER (WHERE p.product_id IS NULL), count(*) "
         "FROM complaints c LEFT JOIN products p ON p.product_id = c.affected_product_id "
         "WHERE c.affected_product_id IS NOT NULL"),
        # Existence is not enough: a complaint cannot use another customer's
        # product for serving, authorization or labels. Keep the row and warn.
        ("customer_owns_affected_product", ["products"],
         "SELECT count(*) FILTER (WHERE p.customer_id <> c.customer_id), count(*) "
         "FROM complaints c JOIN products p ON p.product_id = c.affected_product_id"),
        ("fk_related_branch", ["branches"],
         "SELECT count(*) FILTER (WHERE b.branch_id IS NULL), count(*) "
         "FROM complaints c LEFT JOIN branches b ON b.branch_id = c.related_branch_id "
         "WHERE c.related_branch_id IS NOT NULL"),
        ("fk_origin_interaction", ["call_center_interactions"],
         "SELECT count(*) FILTER (WHERE i.interaction_id IS NULL), count(*) "
         "FROM complaints c LEFT JOIN call_center_interactions i ON i.interaction_id = c.origin_interaction_id "
         "WHERE c.origin_interaction_id IS NOT NULL"),
        # service_agents is outside the supported registry; the quality report
        # records this check as not run unless that parent is already present.
        ("fk_assigned_agent", ["service_agents"],
         "SELECT count(*) FILTER (WHERE a.agent_id IS NULL), count(*) "
         "FROM complaints c LEFT JOIN service_agents a ON a.agent_id = c.assigned_agent_id "
         "WHERE c.assigned_agent_id IS NOT NULL"),
    ],
}


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Customer(_Model):
    customer_id: str
    document_number: str
    document_type: str
    first_name: str
    last_name: str
    date_of_birth: date
    city: str
    state: str
    country: str
    segment: str
    credit_score: Optional[int] = None
    estimated_monthly_income: Optional[Decimal] = None
    registration_date: datetime
    registration_branch_id: str
    customer_status: str
    last_updated: datetime
    accepts_marketing: bool


class Product(_Model):
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
    has_linked_app: bool
    days_past_due: Optional[int] = None
    last_transaction_date: Optional[datetime] = None
    last_updated: datetime


class Branch(_Model):
    branch_id: str
    branch_code: str
    branch_name: str
    branch_type: str
    city: str
    state: str
    country: str
    geographic_zone: str
    phone: str
    branch_status: str


class Transaction(_Model):
    transaction_id: str
    transaction_date: datetime
    process_date: date
    product_id: str
    customer_id: str
    transaction_type: str
    amount: Decimal
    currency: str
    amount_usd: Optional[Decimal] = None
    channel: str
    transaction_country: str
    transaction_status: str
    is_fraud: bool
    fraud_score: Optional[Decimal] = None


class ExchangeRate(_Model):
    date: date
    source_currency: str
    target_currency: str
    exchange_rate: Decimal


class CallCenterInteraction(_Model):
    interaction_id: str
    interaction_date: datetime
    process_date: date
    customer_id: str
    interaction_type: str
    channel: str
    contact_reason: str
    reason_category: str
    duration_seconds: Optional[int] = None
    wait_time_seconds: Optional[int] = None
    was_resolved: Optional[bool] = None
    was_escalated: bool


class CallTranscript(_Model):
    transcript_id: str
    interaction_id: str
    process_date: date
    customer_id: str
    full_text: str
    detected_language: str


class SatisfactionSurvey(_Model):
    survey_id: str
    survey_date: datetime
    process_date: date
    customer_id: str
    survey_type: str
    main_score: int


class Complaint(_Model):
    complaint_id: str
    creation_date: datetime
    process_date: date
    customer_id: str
    case_type: str
    category: str
    subcategory: Optional[str] = None
    reception_channel: str
    affected_product_id: Optional[str] = None
    related_branch_id: Optional[str] = None
    origin_interaction_id: Optional[str] = None
    description: str
    claimed_amount: Optional[Decimal] = None
    currency: Optional[str] = None
    priority: str
    status: str
    assigned_agent_id: Optional[str] = None
    assignment_date: Optional[datetime] = None
    first_response_date: Optional[datetime] = None
    resolution_date: Optional[datetime] = None
    closing_date: Optional[datetime] = None
    sla_breached: bool
    resolution_days: Optional[int] = None
    resolution: Optional[str] = None
    compensation_granted: Optional[Decimal] = None
    resolution_satisfaction: Optional[int] = None
    is_repeat_complainer: bool


ROW_MODELS = {
    "customers": Customer,
    "products": Product,
    "branches": Branch,
    "transactions": Transaction,
    "daily_exchange_rates": ExchangeRate,
    "call_center_interactions": CallCenterInteraction,
    "call_transcripts": CallTranscript,
    "satisfaction_surveys": SatisfactionSurvey,
    "complaints": Complaint,
}
