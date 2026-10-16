.PHONY: up test lint

# dev loop: build, start and sync code changes into containers (see develop.watch in compose.yaml).
# --build: watch syncs only files changed after start, so a stale image would run old code; cached layers keep it fast
up:
	docker compose up --watch --build

SERVICES := harness testing-wms testing-wms-mcp

test:
	for s in $(SERVICES); do uv run --directory services/$$s pytest -q || exit 1; done

# check only, no rewrites: lint rules, formatting drift (fix with `ruff check --fix` / `ruff format`), types
lint:
	for s in $(SERVICES); do \
		uv run --directory services/$$s ruff check . && \
		uv run --directory services/$$s ruff format --check . && \
		uv run --directory services/$$s basedpyright || exit 1; \
	done
