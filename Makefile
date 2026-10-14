.PHONY: up test lint

# dev loop: build, start and sync code changes into containers (see develop.watch in compose.yaml)
up:
	docker compose up --watch

test:
	uv run --directory services/harness pytest -q

# check only, no rewrites: lint rules + formatting drift (fix with `ruff check --fix` / `ruff format`)
lint:
	uv run --directory services/harness ruff check .
	uv run --directory services/harness ruff format --check .
