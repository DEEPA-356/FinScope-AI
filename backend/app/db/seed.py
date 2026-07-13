"""
Database seeder — creates sample data for development.

Run with: docker compose exec backend python -m app.db.seed
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from datetime import datetime, timedelta, timezone
import random

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.db.models import (
    Account, AccountType, Goal, GoalType, Transaction,
    TransactionCategory, TransactionType, User, UserRole
)


SAMPLE_TRANSACTIONS = [
    ("Whole Foods Market", TransactionCategory.groceries, 89.45),
    ("Netflix", TransactionCategory.entertainment, 15.99),
    ("Shell Gas Station", TransactionCategory.transport, 65.00),
    ("Amazon.com", TransactionCategory.shopping, 124.30),
    ("Dr. Smith Clinic", TransactionCategory.health, 50.00),
    ("Starbucks", TransactionCategory.food_dining, 8.75),
    ("Con Edison", TransactionCategory.utilities, 145.00),
    ("Payroll Deposit", TransactionCategory.income, 4500.00),
    ("Chipotle", TransactionCategory.food_dining, 13.50),
    ("Spotify", TransactionCategory.entertainment, 9.99),
    ("CVS Pharmacy", TransactionCategory.health, 32.15),
    ("Uber", TransactionCategory.transport, 22.40),
    ("Costco", TransactionCategory.groceries, 187.60),
    ("Southwest Airlines", TransactionCategory.travel, 320.00),
    ("Chase Bank ATM", TransactionCategory.other, 200.00),
]


async def seed(db: AsyncSession) -> None:
    """Seed sample user, account, and transactions."""

    print("🌱 Seeding database...")

    # Admin user
    admin = User(
        email="admin@finscope.ai",
        hashed_password=hash_password("Admin123!"),
        full_name="Admin User",
        role=UserRole.admin,
        is_active=True,
        is_verified=True,
    )
    db.add(admin)

    # Sample end user
    sample_user = User(
        email="demo@finscope.ai",
        hashed_password=hash_password("Demo123!"),
        full_name="Alex Johnson",
        role=UserRole.user,
        is_active=True,
        is_verified=True,
    )
    db.add(sample_user)
    await db.flush()

    # Account
    account = Account(
        user_id=sample_user.id,
        account_name="Chase Checking",
        institution_name="Chase Bank",
        account_type=AccountType.checking,
        currency_code="USD",
        current_balance=Decimal("4823.50"),
        is_primary=True,
    )
    db.add(account)
    await db.flush()

    # Goal
    goal = Goal(
        user_id=sample_user.id,
        title="Emergency Fund",
        goal_type=GoalType.savings,
        target_amount=Decimal("10000.00"),
        current_amount=Decimal("3200.00"),
        currency_code="USD",
        target_date=datetime.now(tz=timezone.utc) + timedelta(days=365),
    )
    db.add(goal)

    # Transactions — last 90 days
    now = datetime.now(tz=timezone.utc)
    for i in range(90):
        # 1-3 transactions per day
        for _ in range(random.randint(1, 3)):
            merchant, category, base_amount = random.choice(SAMPLE_TRANSACTIONS)
            amount = Decimal(str(round(base_amount * random.uniform(0.8, 1.2), 2)))
            tx_type = TransactionType.credit if category == TransactionCategory.income else TransactionType.debit

            tx = Transaction(
                account_id=account.id,
                transaction_date=now - timedelta(days=i, hours=random.randint(0, 23)),
                description=merchant,
                merchant_name=merchant,
                amount_raw=amount,
                amount_usd=amount,
                currency_code="USD",
                transaction_type=tx_type,
                category=category,
                source="seed",
            )
            db.add(tx)

    await db.commit()
    print("✅ Seed complete!")
    print("   Admin:  admin@finscope.ai / Admin123!")
    print("   Demo:   demo@finscope.ai  / Demo123!")


async def main() -> None:
    async with AsyncSessionLocal() as db:
        await seed(db)


if __name__ == "__main__":
    asyncio.run(main())
