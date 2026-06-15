.PHONY: help dev dev-backend dev-frontend test test-cov lint build clean docker-up docker-down docker-build

# Load nvm if available (for npm/node)
NVM_DIR := $(HOME)/.nvm
SHELL := /bin/bash
export PATH := $(NVM_DIR)/versions/node/v22.22.0/bin:$(PATH)

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ─── Development ───────────────────────────────────────────────

dev: ## Start backend + frontend (two processes)
	@echo "Starting backend on :8000 and frontend on :5173..."
	@make dev-backend & make dev-frontend & wait

dev-backend: ## Start Python backend (FastAPI + scheduler)
	uv run python -m stake_watch.main

dev-frontend: ## Start React frontend dev server
	cd frontend && npm run dev

# ─── Testing ───────────────────────────────────────────────────

test: ## Run all tests
	uv run pytest tests/ -v --tb=short

test-cov: ## Run tests with coverage report
	uv run pytest tests/ --cov=stake_watch --cov-report=term-missing

test-watch: ## Run tests in watch mode (requires pytest-watch)
	uv run ptw tests/ -- -v --tb=short

# ─── Build ─────────────────────────────────────────────────────

build-frontend: ## Build React frontend for production
	cd frontend && npm run build

install: ## Install all dependencies
	uv sync
	cd frontend && npm install

# ─── Docker ────────────────────────────────────────────────────

docker-build: ## Build Docker images
	docker compose build

docker-up: ## Start all services
	docker compose up -d

docker-down: ## Stop all services
	docker compose down

docker-logs: ## Tail logs from all services
	docker compose logs -f

docker-restart: ## Restart all services
	docker compose restart

# ─── Database ──────────────────────────────────────────────────

db-shell: ## Open SQLite shell
	sqlite3 stake_watch.db

db-vacuum: ## Vacuum and optimize DB
	sqlite3 stake_watch.db "PRAGMA wal_checkpoint(TRUNCATE); VACUUM;"

# ─── Cleanup ───────────────────────────────────────────────────

clean: ## Remove build artifacts and caches
	rm -rf __pycache__ .pytest_cache .coverage htmlcov dist
	rm -rf frontend/dist frontend/node_modules/.vite
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
