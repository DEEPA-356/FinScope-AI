# FinScope AI — Intelligent Personal Finance Analytics Platform

> A production-grade fintech analytics platform: ML-powered spending intelligence, forecasting, fraud detection, and a natural-language financial assistant — all served via a Serverless Python API and React dashboard.

[![CI](https://github.com/DEEPA-356/FinScope-AI/actions/workflows/ci.yml/badge.svg)](https://github.com/DEEPA-356/FinScope-AI/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Serverless Architecture Overview

This project uses a 100% free-tier serverless architecture with no credit cards required.

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        FinScope AI Platform                            │
│                                                                        │
│  ┌─────────────────┐       ┌────────────────────┐      ┌────────────┐  │
│  │     Vercel      │       │       Vercel       │      │  Supabase  │  │
│  │ Static Hosting  │──────▶│ Serverless Python  │─────▶│ PostgreSQL │  │
│  │ (React/Vite UI) │       │ (FastAPI /api/*)   │      │ (Port 6543)│  │
│  └─────────────────┘       └────────────────────┘      └────────────┘  │
│                                      ▲                                 │
│                                      │                                 │
│                            ┌────────────────────┐                      │
│                            │   GitHub Actions   │                      │
│                            │ (Nightly ML Cron)  │                      │
│                            └────────────────────┘                      │
└────────────────────────────────────────────────────────────────────────┘
```

## Tech Stack

| Layer | Technology |
|---|---|
| **API** | Python 3.11, FastAPI, Vercel Serverless |
| **Database** | PostgreSQL 15 (Supabase), SQLAlchemy 2.0, Alembic |
| **Cron Jobs** | GitHub Actions (Paginated REST calls) |
| **ML** | Pandas, Scikit-learn, XGBoost, Prophet, SHAP |
| **Frontend** | React 18, TypeScript, Vite, TailwindCSS, shadcn/ui |
| **Auth** | JWT (access + refresh), OAuth2 password flow |
| **Hosting** | Vercel (Single Project for Frontend + Backend API) |

## Known Trade-offs

### Vercel Serverless Constraints
1. **Cold Starts:** The very first API request after a period of inactivity may take a few seconds longer as the Vercel Python runtime spins up.
2. **AI Chat Streaming:** Vercel's free tier caps execution time to ~10s and does not support persistent WebSockets for serverless functions. The AI Assistant chat endpoint (`/api/v1/chat/message`) has been implemented as a standard synchronous POST request. The frontend displays a loading state until the full response is generated and returned.

## Quickstart (Local Dev)

While the app is deployed serverless, we maintain legacy Docker files in the `local-dev/` folder if you prefer running it locally via containers.

### Prerequisites
- Node.js ≥ 20 (for frontend dev)
- Python 3.11 (for backend dev)
- Supabase account (for database)

### 1. Clone & Configure

```bash
git clone https://github.com/DEEPA-356/FinScope-AI.git
cd FinScope-AI
```

Create a `.env` file in the `backend/` directory using your Supabase pooled connection string:
```env
DATABASE_URL=postgres://[user]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres
```

### 2. Run Backend (FastAPI)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r ../requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 3. Run Frontend (React)

```bash
cd frontend
npm install
npm run dev
```

For full deployment instructions, please see [DEPLOYMENT.md](DEPLOYMENT.md).

## License

[MIT](LICENSE) — © 2026 FinScope AI
