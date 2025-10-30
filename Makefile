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

dev-frontend:
	@echo "Starting frontend dev server..."
	cd frontend-src && npm install && npm run dev

build-docker:
	@echo "Building Docker image..."
	./scripts/build_and_push_container_image.sh

.PHONY: test-unit test-e2e test-e2e-payments lint format dev-frontend build-docker
