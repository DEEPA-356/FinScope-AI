# FinScope AI — Intelligent Personal Finance Analytics Platform

> A production-grade fintech analytics platform: ML-powered spending intelligence, forecasting, fraud detection, and a natural-language financial assistant — all served through a real API and React dashboard.

[![CI](https://github.com/your-org/finscope-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/your-org/finscope-ai/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        FinScope AI Platform                         │
│                                                                     │
│  ┌──────────────┐     ┌──────────────────┐     ┌────────────────┐  │
│  │   React 18   │────▶│  FastAPI Backend │────▶│  PostgreSQL    │  │
│  │  TypeScript  │     │   (Port 8000)    │     │  (Port 5432)   │  │
│  │  Vite + TW   │     │                  │     └────────────────┘  │
│  │  (Port 5173) │     │  ┌────────────┐  │     ┌────────────────┐  │
│  └──────────────┘     │  │   Celery   │  │────▶│     Redis      │  │
│                        │  │  Workers   │  │     │  (Port 6379)   │  │
│  ┌──────────────┐     │  └────────────┘  │     └────────────────┘  │
│  │  ML Pipeline │────▶│                  │     ┌────────────────┐  │
│  │  (Airflow /  │     │  ┌────────────┐  │────▶│    MLflow      │  │
│  │   Prefect)   │     │  │   MLflow   │  │     │  (Port 5000)   │  │
│  └──────────────┘     │  │  Registry  │  │     └────────────────┘  │
│                        │  └────────────┘  │                         │
│                        └──────────────────┘                         │
└─────────────────────────────────────────────────────────────────────┘
```

## Tech Stack

| Layer | Technology |
|---|---|
| **API** | Python 3.11, FastAPI, Uvicorn |
| **Database** | PostgreSQL 15, SQLAlchemy 2.0, Alembic |
| **Cache / Queue** | Redis 7, Celery 5, Flower |
| **ML** | Pandas, Scikit-learn, XGBoost, LightGBM, Prophet, SHAP |
| **Experiment Tracking** | MLflow |
| **Data Validation** | Great Expectations |
| **Frontend** | React 18, TypeScript, Vite, TailwindCSS, shadcn/ui |
| **Auth** | JWT (access + refresh), OAuth2 password flow, RBAC |
| **Observability** | Prometheus, Grafana, Sentry |
| **CI/CD** | GitHub Actions → Render/Railway (API) + Vercel (UI) |

## Quickstart (Local Dev)

### Prerequisites

- Docker Desktop ≥ 24
- Node.js ≥ 20 (for frontend dev without Docker)
- Python 3.11 (for backend dev without Docker)
- `make` (optional, for Makefile shortcuts)

### 1. Clone & configure

```bash
git clone https://github.com/your-org/finscope-ai.git
cd finscope-ai
cp .env.example .env
# Edit .env with your secrets (see .env.example for all required vars)
```

### 2. Start all services

```bash
docker compose up --build
```

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| API Docs (ReDoc) | http://localhost:8000/redoc |
| Flower (Celery UI) | http://localhost:5555 |
| MLflow UI | http://localhost:5000 |
| Grafana | http://localhost:3000 |
| Prometheus | http://localhost:9090 |

### 3. Run database migrations

```bash
docker compose exec backend alembic upgrade head
```

### 4. Seed sample data

```bash
docker compose exec backend python -m app.db.seed
```

## Project Structure

```
finscope-ai/
├── backend/                  # FastAPI application
│   ├── app/
│   │   ├── api/              # Route handlers (auth, transactions, ml, ...)
│   │   ├── core/             # Config, security, logging
│   │   ├── db/               # SQLAlchemy models, session, seed
│   │   ├── schemas/          # Pydantic schemas
│   │   ├── services/         # Business logic
│   │   ├── ml/               # Model training & inference
│   │   ├── tasks/            # Celery task definitions
│   │   └── main.py
│   ├── tests/
│   ├── alembic/
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                 # React + TypeScript app
│   ├── src/
│   │   ├── pages/
│   │   ├── components/
│   │   ├── hooks/
│   │   ├── api/
│   │   └── App.tsx
│   ├── package.json
│   └── Dockerfile
├── ml-pipeline/              # R&D notebooks + production DAGs
│   ├── notebooks/
│   ├── pipelines/
│   └── mlruns/
├── data/
│   ├── raw/
│   ├── processed/
│   └── external/
├── infra/
│   ├── docker-compose.yml    # (symlinked to root)
│   ├── prometheus/
│   ├── grafana/
│   └── k8s/
├── docs/
│   ├── architecture-diagram.md
│   ├── er-diagram.md
│   ├── api-reference.md
│   └── runbook.md
├── .github/
│   └── workflows/
│       └── ci.yml
├── docker-compose.yml
├── .env.example
├── .pre-commit-config.yaml
├── Makefile
└── LICENSE
```

## Development

### Backend (without Docker)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend (without Docker)

```bash
cd frontend
npm install
npm run dev
```

### Running tests

```bash
# Backend
cd backend && pytest --cov=app --cov-report=term-missing

# Frontend
cd frontend && npm test
```

### Pre-commit hooks

```bash
pip install pre-commit
pre-commit install
pre-commit run --all-files   # manual run
```

## Build Phases

| Phase | Description | Status |
|---|---|---|
| 0 | Project scaffolding | ✅ Complete |
| 1 | Database design (ER + SQLAlchemy + Alembic) | 🔜 Next |
| 2 | Data ingestion & cleaning pipeline | — |
| 3 | Feature engineering pipeline | — |
| 4 | Auth & core API | — |
| 5 | ML services | — |
| 6 | Explainability & recommendations API | — |
| 7 | Fraud/anomaly detection + alerting | — |
| 8 | Frontend application | — |
| 9 | FinScope Assistant (RAG chatbot) | — |
| 10 | BI layer & executive reporting | — |
| 11 | Testing & observability | — |
| 12 | CI/CD & deployment | — |
| 13 | Documentation & portfolio packaging | — |

## Contributing

See [docs/runbook.md](docs/runbook.md) for the development workflow and branching strategy.

## License

[MIT](LICENSE) — © 2025 FinScope AI
