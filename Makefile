# Sparr — common tasks (PLAN.md §11)
.PHONY: init migrate test backend frontend up up-dev down lint

init:            ## first-time setup: deps + migrate + seed
	cd backend && uv sync
	cd frontend && npm install
	$(MAKE) migrate

migrate:         ## run migrations
	cd backend && uv run python manage.py migrate

test:            ## backend tests
	cd backend && uv run python manage.py test

backend:         ## dev server (backend)
	cd backend && uv run python manage.py runserver

frontend:        ## dev server (frontend)
	cd frontend && npm run dev

up:              ## full local stack (版本 A)
	docker compose up --build

up-dev:          ## dev stack with hot reload
	docker compose -f docker-compose.dev.yml up --build

down:            ## stop dev stack
	docker compose -f docker-compose.dev.yml down
