# FinScope AI — ER Diagram & Database Schema

## Entity-Relationship Overview

```
users
  │
  ├──< accounts (1:many)
  │       │
  │       ├──< cards (1:many)
  │       │
  │       └──< transactions (1:many)
  │               │
  │               └──< transaction_tags (many:many via join table)
  │
  ├──< goals (1:many)
  │
  ├──< alerts (1:many)
  │
  ├──< features (1:1 per user — materialized ML features)
  │
  ├──< model_runs (1:many — audit trail of ML executions)
  │
  ├──< forecasts (1:many)
  │
  └──< recommendations (1:many)
```

## Design Decisions

| Decision | Options | Choice | Reason |
|---|---|---|---|
| **Primary keys** | UUID vs BIGSERIAL | UUID (uuid-ossp) | Distributed-safe, no enumeration attacks, works with sharding |
| **Soft delete** | `deleted_at` nullable timestamp | ✅ Used on users, accounts, transactions | Audit compliance, data recovery |
| **Transactions partitioning** | No partition vs range by date | Range partition by `transaction_date` year-month | Expected 10M+ rows; monthly partitions keep index size manageable |
| **Features table** | Wide table vs JSONB | JSONB column + typed columns for ML inputs | Flexible for adding features without migrations; typed cols for query performance |
| **Currency** | Store raw + normalized | Both: `amount_raw`, `currency_code`, `amount_usd` | Phase 8 FX normalization writes `amount_usd`; raw preserved for audit |
