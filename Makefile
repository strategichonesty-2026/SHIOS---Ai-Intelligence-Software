.PHONY: help install test lint bootstrap run api up down logs migrate reset frontend

help:
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "};{printf "  %-12s %s\n", $$1, $$2}'

install:  ## install backend dev dependencies
	cd backend && pip install -r requirements-dev.txt

test:  ## run the backend test suite
	cd backend && pytest -q

lint:  ## lint and type-check the backend
	cd backend && ruff check app tests && mypy app

bootstrap:  ## create the schema and run one full intelligence loop (SQLite)
	cd backend && DATABASE_URL=sqlite+pysqlite:///./shios.db python -m app.cli bootstrap

run:  ## run one full loop against the configured database
	cd backend && python -m app.cli run --mode full

api:  ## serve the API locally with reload
	cd backend && uvicorn app.main:app --reload --port 8000

migrate:  ## apply database migrations
	cd backend && alembic upgrade head

reset:  ## drop and recreate the schema
	cd backend && python -m app.cli reset --yes

frontend:  ## run the dashboard in development mode
	cd frontend && npm run dev

up:  ## start the full stack
	docker compose up --build -d

down:  ## stop the full stack
	docker compose down

logs:  ## follow backend logs
	docker compose logs -f backend
