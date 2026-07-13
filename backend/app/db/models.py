"""
SQLAlchemy ORM models — all tables in the FinScope schema.

Import order matters for FK resolution:
  users → accounts → cards → transactions
                           → features
                           → model_runs → forecasts
                           → recommendations
                           → alerts
                           → goals
"""

from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import SoftDeleteMixin, TimestampMixin, UUIDMixin


# ─────────────────────────────────────────────────────────────────────────────
# Enumerations
# ─────────────────────────────────────────────────────────────────────────────

class UserRole(str, enum.Enum):
    admin = "admin"
    analyst = "analyst"
    user = "user"


class AccountType(str, enum.Enum):
    checking = "checking"
    savings = "savings"
    credit = "credit"
    investment = "investment"
    loan = "loan"


class TransactionType(str, enum.Enum):
    debit = "debit"
    credit = "credit"


class TransactionCategory(str, enum.Enum):
    food_dining = "food_dining"
    groceries = "groceries"
    transport = "transport"
    utilities = "utilities"
    housing = "housing"
    entertainment = "entertainment"
    health = "health"
    shopping = "shopping"
    travel = "travel"
    education = "education"
    income = "income"
    transfer = "transfer"
    other = "other"


class GoalType(str, enum.Enum):
    savings = "savings"
    spending_limit = "spending_limit"
    debt_payoff = "debt_payoff"
    investment = "investment"


class GoalStatus(str, enum.Enum):
    active = "active"
    completed = "completed"
    paused = "paused"
    failed = "failed"


class AlertType(str, enum.Enum):
    overspending = "overspending"
    low_balance = "low_balance"
    goal_milestone = "goal_milestone"
    anomaly = "anomaly"
    large_transaction = "large_transaction"
    bill_due = "bill_due"


class AlertChannel(str, enum.Enum):
    email = "email"
    sms = "sms"
    in_app = "in_app"


class AlertStatus(str, enum.Enum):
    pending = "pending"
    sent = "sent"
    failed = "failed"
    dismissed = "dismissed"


class RiskLevel(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class ModelRunStatus(str, enum.Enum):
    running = "running"
    completed = "completed"
    failed = "failed"


# ─────────────────────────────────────────────────────────────────────────────
# User
# ─────────────────────────────────────────────────────────────────────────────

class User(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """
    Platform user — supports multi-tenancy.

    Each user owns their accounts, transactions, and ML outputs.
    Roles: admin (full access), analyst (read-all), user (own data).
    """

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        Index("ix_users_email_active", "email", postgresql_where="deleted_at IS NULL"),
    )

    email: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"), default=UserRole.user, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    phone_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    timezone: Mapped[str] = mapped_column(String(50), default="UTC", nullable=False)
    base_currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    notification_email: Mapped[bool] = mapped_column(Boolean, default=True)
    notification_sms: Mapped[bool] = mapped_column(Boolean, default=False)
    notification_in_app: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    accounts: Mapped[list[Account]] = relationship(
        "Account", back_populates="user", cascade="all, delete-orphan"
    )
    goals: Mapped[list[Goal]] = relationship(
        "Goal", back_populates="user", cascade="all, delete-orphan"
    )
    alerts: Mapped[list[Alert]] = relationship(
        "Alert", back_populates="user", cascade="all, delete-orphan"
    )
    features: Mapped[UserFeatures | None] = relationship(
        "UserFeatures", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    model_runs: Mapped[list[ModelRun]] = relationship(
        "ModelRun", back_populates="user"
    )
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        "RefreshToken", back_populates="user", cascade="all, delete-orphan"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Auth — Refresh Token store
# ─────────────────────────────────────────────────────────────────────────────

class RefreshToken(UUIDMixin, TimestampMixin, Base):
    """
    Persisted refresh tokens for JWT rotation.

    Storing tokens in DB (vs stateless) enables revocation on logout/password-change.
    """

    __tablename__ = "refresh_tokens"

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)

    user: Mapped[User] = relationship("User", back_populates="refresh_tokens")


# ─────────────────────────────────────────────────────────────────────────────
# Account
# ─────────────────────────────────────────────────────────────────────────────

class Account(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """
    Financial account (bank/credit card/investment) linked to a user.

    One user may have multiple accounts across institutions.
    """

    __tablename__ = "accounts"
    __table_args__ = (
        Index("ix_accounts_user_id", "user_id"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    account_name: Mapped[str] = mapped_column(String(255), nullable=False)
    institution_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    account_type: Mapped[AccountType] = mapped_column(
        Enum(AccountType, name="account_type"), nullable=False
    )
    account_number_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    currency_code: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    current_balance: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), default=Decimal("0.00"), nullable=False
    )
    credit_limit: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, nullable=False)

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="accounts")
    cards: Mapped[list[Card]] = relationship(
        "Card", back_populates="account", cascade="all, delete-orphan"
    )
    transactions: Mapped[list[Transaction]] = relationship(
        "Transaction", back_populates="account"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Card
# ─────────────────────────────────────────────────────────────────────────────

class Card(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """
    Payment card associated with an account.

    Maps to the Cards dataset (card-level spend analytics).
    """

    __tablename__ = "cards"

    account_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    card_number_last4: Mapped[str] = mapped_column(String(4), nullable=False)
    card_network: Mapped[str | None] = mapped_column(String(50), nullable=True)  # Visa, MC, Amex
    card_type: Mapped[str | None] = mapped_column(String(50), nullable=True)      # debit, credit
    expiry_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expiry_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    spending_limit_daily: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    spending_limit_monthly: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    # Relationships
    account: Mapped[Account] = relationship("Account", back_populates="cards")
    transactions: Mapped[list[Transaction]] = relationship("Transaction", back_populates="card")


# ─────────────────────────────────────────────────────────────────────────────
# Transaction
# ─────────────────────────────────────────────────────────────────────────────

class Transaction(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """
    Core transaction record — the heart of the analytics system.

    Stores both raw currency amounts and USD-normalized amounts.
    ML labels (category_predicted, is_anomaly) are written by the ML pipeline.

    Why both account_id and card_id?
      - Account is always required (for balance tracking)
      - Card is optional (cash/wire transactions have no card)
    """

    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_user_account", "account_id", "transaction_date"),
        Index("ix_transactions_category", "category"),
        Index("ix_transactions_anomaly", "is_anomaly", postgresql_where="is_anomaly = true"),
        CheckConstraint("amount_raw > 0", name="ck_transactions_positive_amount"),
    )

    account_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    card_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("cards.id", ondelete="SET NULL"), nullable=True
    )

    # Transaction core
    transaction_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    merchant_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    merchant_category_code: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Amounts (raw + normalized)
    amount_raw: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    amount_usd: Mapped[Decimal | None] = mapped_column(Numeric(15, 4), nullable=True)
    fx_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)

    # Classification
    transaction_type: Mapped[TransactionType] = mapped_column(
        Enum(TransactionType, name="transaction_type"), nullable=False
    )
    category: Mapped[TransactionCategory | None] = mapped_column(
        Enum(TransactionCategory, name="transaction_category"), nullable=True
    )
    category_predicted: Mapped[str | None] = mapped_column(String(50), nullable=True)
    category_confidence: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)

    # ML flags
    is_anomaly: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    anomaly_score: Mapped[float | None] = mapped_column(Numeric(8, 6), nullable=True)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_internal_transfer: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Source tracking
    source: Mapped[str] = mapped_column(String(50), default="manual", nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_data: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # Relationships
    account: Mapped[Account | None] = relationship("Account", back_populates="transactions")
    card: Mapped[Card | None] = relationship("Card", back_populates="transactions")


# ─────────────────────────────────────────────────────────────────────────────
# User Features (materialized ML feature store)
# ─────────────────────────────────────────────────────────────────────────────

class UserFeatures(UUIDMixin, TimestampMixin, Base):
    """
    Materialized feature store — one row per user, recomputed by Celery daily.

    Typed columns for the most-queried ML inputs;
    JSONB `extra_features` for experimental/phase-specific features.

    Business interpretation: This table IS the "financial fingerprint" of
    each user — it's what the ML models actually see at inference time.
    """

    __tablename__ = "user_features"

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True
    )
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # ── Spending features ────────────────────────────────────────────────────
    avg_monthly_spend: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    avg_transaction_value: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    total_transactions_30d: Mapped[int | None] = mapped_column(Integer)
    total_spend_30d: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    total_spend_90d: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    spend_volatility: Mapped[float | None] = mapped_column(Numeric(10, 6))

    # ── Income features ──────────────────────────────────────────────────────
    avg_monthly_income: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    income_stability_score: Mapped[float | None] = mapped_column(Numeric(5, 4))

    # ── Financial health ─────────────────────────────────────────────────────
    financial_health_score: Mapped[float | None] = mapped_column(Numeric(5, 2))  # 0-100
    savings_rate: Mapped[float | None] = mapped_column(Numeric(5, 4))            # 0-1
    debt_to_income_ratio: Mapped[float | None] = mapped_column(Numeric(8, 4))

    # ── ML scores ────────────────────────────────────────────────────────────
    clv_score: Mapped[float | None] = mapped_column(Numeric(12, 4))
    risk_score: Mapped[float | None] = mapped_column(Numeric(5, 4))             # 0-1
    risk_level: Mapped[RiskLevel | None] = mapped_column(Enum(RiskLevel, name="risk_level"))
    churn_probability: Mapped[float | None] = mapped_column(Numeric(5, 4))
    cluster_id: Mapped[int | None] = mapped_column(Integer)
    cluster_label: Mapped[str | None] = mapped_column(String(100))

    # ── Category spend breakdown (30d) ────────────────────────────────────────
    spend_by_category: Mapped[dict] = mapped_column(JSONB, default=dict)

    # ── Extended / experimental features ─────────────────────────────────────
    extra_features: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Relationship
    user: Mapped[User] = relationship("User", back_populates="features")


# ─────────────────────────────────────────────────────────────────────────────
# Model Run (ML experiment audit trail)
# ─────────────────────────────────────────────────────────────────────────────

class ModelRun(UUIDMixin, TimestampMixin, Base):
    """
    Audit trail for every ML model invocation.

    Stores the model name, version, input hash, output, and MLflow run ID.
    This is the link between the FastAPI inference layer and MLflow registry.
    """

    __tablename__ = "model_runs"
    __table_args__ = (
        Index("ix_model_runs_user_model", "user_id", "model_name"),
    )

    user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mlflow_run_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[ModelRunStatus] = mapped_column(
        Enum(ModelRunStatus, name="model_run_status"), nullable=False, default=ModelRunStatus.running
    )
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict)
    parameters: Mapped[dict] = mapped_column(JSONB, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Numeric(10, 3), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user: Mapped[User | None] = relationship("User", back_populates="model_runs")
    forecasts: Mapped[list[Forecast]] = relationship("Forecast", back_populates="model_run")


# ─────────────────────────────────────────────────────────────────────────────
# Forecast
# ─────────────────────────────────────────────────────────────────────────────

class Forecast(UUIDMixin, TimestampMixin, Base):
    """
    Spending / income forecast for a user, generated by Prophet/ARIMA.

    Stores point estimate + confidence intervals for charting.
    """

    __tablename__ = "forecasts"
    __table_args__ = (
        Index("ix_forecasts_user_date", "user_id", "forecast_date"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model_run_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("model_runs.id", ondelete="SET NULL"), nullable=True
    )
    forecast_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)  # None = total
    forecast_type: Mapped[str] = mapped_column(String(50), nullable=False)   # "spending" | "income"
    amount_predicted: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    amount_lower_80: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    amount_upper_80: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    amount_lower_95: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    amount_upper_95: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    currency_code: Mapped[str] = mapped_column(String(3), default="USD")

    # Relationships
    user: Mapped[User] = relationship("User")
    model_run: Mapped[ModelRun | None] = relationship("ModelRun", back_populates="forecasts")


# ─────────────────────────────────────────────────────────────────────────────
# Recommendation
# ─────────────────────────────────────────────────────────────────────────────

class Recommendation(UUIDMixin, TimestampMixin, Base):
    """
    Personalized financial recommendation generated by the ML service.

    Examples: "Reduce dining spend by 20%", "Open a high-yield savings account".
    Tracks user engagement (viewed, acted on, dismissed).
    """

    __tablename__ = "recommendations"
    __table_args__ = (
        Index("ix_recommendations_user_active", "user_id", "is_active"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=5, nullable=False)  # 1=highest
    potential_savings: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_viewed: Mapped[bool] = mapped_column(Boolean, default=False)
    viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_acted_on: Mapped[bool] = mapped_column(Boolean, default=False)
    acted_on_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    shap_explanation: Mapped[dict] = mapped_column(JSONB, default=dict)

    user: Mapped[User] = relationship("User")


# ─────────────────────────────────────────────────────────────────────────────
# Goal
# ─────────────────────────────────────────────────────────────────────────────

class Goal(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """
    User-defined financial goal with progress tracking.

    The Celery beat job updates `current_amount` daily and fires
    milestone alerts via the Alert table.
    """

    __tablename__ = "goals"

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    goal_type: Mapped[GoalType] = mapped_column(Enum(GoalType, name="goal_type"), nullable=False)
    status: Mapped[GoalStatus] = mapped_column(
        Enum(GoalStatus, name="goal_status"), default=GoalStatus.active
    )
    target_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    current_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0.00"))
    currency_code: Mapped[str] = mapped_column(String(3), default="USD")
    target_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    category: Mapped[str | None] = mapped_column(String(50))  # for spending_limit goals
    linked_account_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )

    @property
    def progress_pct(self) -> float:
        if self.target_amount == 0:
            return 0.0
        return float(self.current_amount / self.target_amount * 100)

    user: Mapped[User] = relationship("User", back_populates="goals")


# ─────────────────────────────────────────────────────────────────────────────
# Alert
# ─────────────────────────────────────────────────────────────────────────────

class Alert(UUIDMixin, TimestampMixin, Base):
    """
    System-generated notification for the user.

    Created by Celery tasks (overspend check, anomaly detection, goal milestones).
    Dispatched via email/SMS/in-app depending on user preferences.
    """

    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_user_status", "user_id", "status"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alert_type: Mapped[AlertType] = mapped_column(Enum(AlertType, name="alert_type"), nullable=False)
    channel: Mapped[AlertChannel] = mapped_column(
        Enum(AlertChannel, name="alert_channel"), nullable=False
    )
    status: Mapped[AlertStatus] = mapped_column(
        Enum(AlertStatus, name="alert_status"), default=AlertStatus.pending
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    related_transaction_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True
    )
    related_goal_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("goals.id", ondelete="SET NULL"), nullable=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_detail: Mapped[str | None] = mapped_column(Text)

    user: Mapped[User] = relationship("User", back_populates="alerts")
