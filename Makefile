.PHONY: up test

# dev loop: build, start and sync code changes into containers (see develop.watch in compose.yaml)
up:
	docker compose up --watch

test:
	uv run --directory services/harness pytest -q
