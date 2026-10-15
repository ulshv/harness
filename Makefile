.PHONY: up test lint

# dev loop: build, start and sync code changes into containers (see develop.watch in compose.yaml)
up:
	docker compose up --watch

SERVICES := harness testing-wms

test:
	for s in $(SERVICES); do uv run --directory services/$$s pytest -q || exit 1; done

# check only, no rewrites: lint rules, formatting drift (fix with `ruff check --fix` / `ruff format`), types
lint:
	for s in $(SERVICES); do \
		uv run --directory services/$$s ruff check . && \
		uv run --directory services/$$s ruff format --check . && \
		uv run --directory services/$$s basedpyright || exit 1; \
	done
