# FinScope AI — Runbook

## Local Development

### First-time setup
```bash
# 1. Clone and configure
git clone <repo-url>
cd finscope-ai
cp .env.example .env
# Edit .env — set SECRET_KEY and POSTGRES_PASSWORD

# 2. Start all services
docker compose up --build

# 3. Run migrations
docker compose exec backend alembic upgrade head

# 4. Seed sample data
docker compose exec backend python -m app.db.seed
```

### Service URLs
| Service | URL | Credentials |
|---|---|---|
| Frontend | http://localhost:5173 | — |
| Backend API | http://localhost:8000/docs | — |
| Flower | http://localhost:5555 | — |
| MLflow | http://localhost:5000 | — |
| Grafana | http://localhost:3000 | admin / admin |
| Prometheus | http://localhost:9090 | — |

### Demo credentials
- **Admin:** `admin@finscope.ai` / `Admin123!`
- **Demo:** `demo@finscope.ai` / `Demo123!`

## Running Tests

```bash
# All tests
make test

# Backend only (with coverage)
make test-backend

# Frontend only
make test-frontend
```

## Database Operations

```bash
# Create migration after model changes
make migrate-create MSG="add column x to users"

# Apply migrations
make migrate

# Reset database (DESTRUCTIVE)
make reset-db
```

## Triggering ML Tasks Manually

```bash
# Open backend shell
make shell-backend

# Recompute features for all users
python -c "from app.tasks.tasks import recompute_all_features; recompute_all_features.delay()"

# Score anomalies for a transaction
python -c "from app.tasks.tasks import score_transaction_anomaly; score_transaction_anomaly.delay('<tx_id>', '<user_id>')"
```

## Deployment

### Backend (Render/Railway)
1. Push to `main` branch — GitHub Actions builds and pushes Docker image
2. Set environment variables in Render dashboard (copy from `.env.example`)
3. Set `APP_ENV=production`, `DEBUG=false`
4. Run migrations: `alembic upgrade head`

### Frontend (Vercel)
1. Connect repo to Vercel
2. Set `VITE_API_BASE_URL=https://your-backend.onrender.com`
3. Deploy from `frontend/` root

## Monitoring

- **API errors:** Sentry dashboard (configure `SENTRY_DSN`)
- **API latency:** Grafana → FinScope API dashboard
- **Celery tasks:** Flower at `:5555`
- **ML experiments:** MLflow at `:5000`
