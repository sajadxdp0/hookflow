SHELL := /bin/bash
.DEFAULT_GOAL := check

.PHONY: install lint test dashboard-install dashboard-typecheck dashboard-build docker-up docker-down check

install:
	uv sync --frozen --extra dev

lint:
	uv run --frozen ruff check .

test:
	uv run --frozen pytest

dashboard-install:
	npm --prefix dashboard ci

dashboard-typecheck:
	npm --prefix dashboard run typecheck

dashboard-build:
	npm --prefix dashboard run build

docker-up:
	docker compose -f docker/docker-compose.yml up --build --detach

docker-down:
	docker compose -f docker/docker-compose.yml down

check: lint test dashboard-install dashboard-typecheck dashboard-build
