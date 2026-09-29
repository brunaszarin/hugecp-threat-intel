.PHONY: help setup db-up db-down ingest api web test lint format

help: ## Lista os comandos disponíveis
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-10s %s\n", $$1, $$2}'

setup: ## Instala dependências do backend e do frontend
	cd backend && uv sync
	cd frontend && npm ci

db-up: ## Sobe o PostgreSQL
	docker compose up -d --wait db

db-down: ## Derruba o PostgreSQL
	docker compose down

ingest: ## Carrega data/flows.csv e data/indicadores.csv no banco (idempotente)
	cd backend && uv run python -m app.ingest --data-dir ../data

api: ## Roda a API em modo desenvolvimento
	cd backend && uv run uvicorn app.main:app --reload

web: ## Roda o frontend em modo desenvolvimento
	cd frontend && npm run dev

test: ## Roda todos os testes (o backend precisa do banco: make db-up)
	cd backend && uv run pytest
	cd frontend && npm test

lint: ## Roda lint e checagem de tipos
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app tests
	cd frontend && npm run lint && npm run typecheck && npm run format:check

format: ## Formata o código
	cd backend && uv run ruff check --fix . && uv run ruff format .
	cd frontend && npm run format
