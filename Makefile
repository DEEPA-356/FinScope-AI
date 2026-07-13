# =============================================================================
# FinScope AI — Makefile
# Convenience wrapper around docker-compose and common dev tasks.
# Requires: make, docker, docker-compose
# =============================================================================

.PHONY: help up down build logs shell-backend shell-frontend \
        migrate seed test-backend test-frontend lint format \
        clean reset-db

DOCKER_COMPOSE := docker compose
BACKEND_SERVICE := backend
FRONTEND_SERVICE := frontend

# ── Default target ───────────────────────────────────────────────────────────
help:  ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Docker ───────────────────────────────────────────────────────────────────
up:  ## Start all services (detached)
	$(DOCKER_COMPOSE) up -d

up-build:  ## Rebuild and start all services
	$(DOCKER_COMPOSE) up --build -d

down:  ## Stop all services
	$(DOCKER_COMPOSE) down

build:  ## Build Docker images without starting
	$(DOCKER_COMPOSE) build

logs:  ## Tail logs for all services
	$(DOCKER_COMPOSE) logs -f

logs-backend:  ## Tail backend logs
	$(DOCKER_COMPOSE) logs -f $(BACKEND_SERVICE)

# ── Database ─────────────────────────────────────────────────────────────────
migrate:  ## Run Alembic migrations
	$(DOCKER_COMPOSE) exec $(BACKEND_SERVICE) alembic upgrade head

migrate-create:  ## Create a new migration (usage: make migrate-create MSG="add users table")
	$(DOCKER_COMPOSE) exec $(BACKEND_SERVICE) alembic revision --autogenerate -m "$(MSG)"

seed:  ## Seed the database with sample data
	$(DOCKER_COMPOSE) exec $(BACKEND_SERVICE) python -m app.db.seed

reset-db:  ## Drop and recreate the database (WARNING: destroys all data)
	$(DOCKER_COMPOSE) down -v
	$(DOCKER_COMPOSE) up -d postgres redis
	sleep 5
	$(DOCKER_COMPOSE) up -d backend
	sleep 5
	$(MAKE) migrate
	$(MAKE) seed

# ── Shells ───────────────────────────────────────────────────────────────────
shell-backend:  ## Open a shell in the backend container
	$(DOCKER_COMPOSE) exec $(BACKEND_SERVICE) bash

shell-frontend:  ## Open a shell in the frontend container
	$(DOCKER_COMPOSE) exec $(FRONTEND_SERVICE) sh

shell-db:  ## Open psql in the postgres container
	$(DOCKER_COMPOSE) exec postgres psql -U finscope_user -d finscope

# ── Testing ──────────────────────────────────────────────────────────────────
test-backend:  ## Run backend pytest suite
	$(DOCKER_COMPOSE) exec $(BACKEND_SERVICE) pytest --cov=app --cov-report=term-missing

test-frontend:  ## Run frontend Vitest suite
	$(DOCKER_COMPOSE) exec $(FRONTEND_SERVICE) npm test

test:  ## Run all tests
	$(MAKE) test-backend
	$(MAKE) test-frontend

# ── Code quality ─────────────────────────────────────────────────────────────
lint:  ## Lint backend (ruff) and frontend (eslint)
	$(DOCKER_COMPOSE) exec $(BACKEND_SERVICE) ruff check app tests
	$(DOCKER_COMPOSE) exec $(FRONTEND_SERVICE) npm run lint

format:  ## Auto-format backend with ruff
	$(DOCKER_COMPOSE) exec $(BACKEND_SERVICE) ruff format app tests

type-check:  ## Type-check backend (mypy) and frontend (tsc)
	$(DOCKER_COMPOSE) exec $(BACKEND_SERVICE) mypy app
	$(DOCKER_COMPOSE) exec $(FRONTEND_SERVICE) npm run type-check

# ── Cleanup ──────────────────────────────────────────────────────────────────
clean:  ## Remove containers, networks, but keep volumes
	$(DOCKER_COMPOSE) down --remove-orphans

clean-all:  ## Remove everything including volumes (WARNING: data loss)
	$(DOCKER_COMPOSE) down -v --remove-orphans
	docker system prune -f
