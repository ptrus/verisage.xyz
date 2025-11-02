SHELL := /bin/bash

test-unit:
	@echo "Running unit tests..."
	uv run pytest tests/unit/ -v

test-e2e:
	@echo "Running E2E tests..."
	cd tests/e2e && ./test-e2e.sh

test-e2e-payments:
	@echo "Running E2E payment tests..."
	cd tests/e2e && ./test-e2e-payments.sh

lint:
	@echo "Running linters..."
	uv run ruff check src/
	uv run ruff format --check src/
	cd frontend-src && npm run lint
	cd frontend-src && npm run format:check

format:
	@echo "Formatting code..."
	uv run ruff format
	uv run ruff check --fix
	cd frontend-src && npm run format

dev-backend:
	@echo "Starting backend with docker compose (server + worker)..."
	docker compose --env-file .env.testnet up

dev-frontend:
	@echo "Starting frontend dev server..."
	cd frontend-src && npm install && VITE_API_URL=http://localhost:8000 npm run dev

dev:
	@echo "Starting both backend and frontend..."
	@echo "Run 'make dev-backend' in one terminal and 'make dev-frontend' in another"
	@echo "Or use: docker compose --env-file .env.testnet up -d && cd frontend-src && VITE_API_URL=http://localhost:8000 npm run dev"

build-docker:
	@echo "Building Docker image..."
	./scripts/build_and_push_container_image.sh

update-compose-image:
	@echo "Building, pushing, and updating compose image digest..."
	UPDATE_COMPOSE_SHA=true PUSH_IMAGE=true OUTPUT_IMAGE_NAME_PATH="/tmp/image-name" ./scripts/build_and_push_container_image.sh

verify-compose-image:
	@echo "Building image and verifying compose digest..."
	@set -euo pipefail; \
		TMP_FILE=$$(mktemp); \
		OUTPUT_IMAGE_NAME_PATH="$$TMP_FILE" ./scripts/build_and_push_container_image.sh; \
		EXPECTED_VERISAGE_IMAGE="$$(cat "$$TMP_FILE")" ./scripts/verify_container_image.sh; \
		rm -f "$$TMP_FILE"

.PHONY: test-unit test-e2e test-e2e-payments lint format dev-backend dev-frontend dev build-docker update-compose-image verify-compose-image
