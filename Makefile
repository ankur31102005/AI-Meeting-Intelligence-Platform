# =====================================================================
# Developer workflow shortcuts.
# Windows users: run these from Git Bash, or copy the underlying
# commands into PowerShell (they are plain `docker compose` / `pytest`).
# =====================================================================

COMPOSE := docker compose --env-file .env -f docker/docker-compose.yml
COMPOSE_PROD := docker compose --env-file .env -f docker/docker-compose.prod.yml

.PHONY: help up down build logs ps restart test test-integration lint fmt prod-up prod-down prod-logs

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

up: ## Start all services (build if needed)
	$(COMPOSE) up -d --build

down: ## Stop all services (keep data volumes)
	$(COMPOSE) down

build: ## Rebuild images
	$(COMPOSE) build

logs: ## Tail logs from all services
	$(COMPOSE) logs -f --tail=100

ps: ## Show service status
	$(COMPOSE) ps

restart: ## Restart backend + worker (after code changes without hot reload)
	$(COMPOSE) restart backend worker

test: ## Run backend unit tests
	python -m pytest tests/backend/unit -v

test-integration: ## Run integration tests (requires `make up` first)
	INTEGRATION_TESTS=1 python -m pytest tests/backend/integration -v

lint: ## Lint backend code
	python -m ruff check backend tests

fmt: ## Auto-format backend code
	python -m ruff format backend tests

prod-up: ## Start the FULL production stack (backend + frontend, built images)
	$(COMPOSE_PROD) up -d --build

prod-down: ## Stop the production stack
	$(COMPOSE_PROD) down

prod-logs: ## Tail production logs
	$(COMPOSE_PROD) logs -f --tail=100
