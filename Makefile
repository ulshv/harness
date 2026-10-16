.PHONY: up test lint api-types

# dev loop: build, start and sync code changes into containers (see develop.watch in compose.yaml).
# --build: watch syncs only files changed after start, so a stale image would run old code; cached layers keep it fast
up:
	docker compose up --watch --build

SERVICES := harness testing-wms testing-wms-mcp

test:
	for s in $(SERVICES); do uv run --directory services/$$s pytest -q || exit 1; done
	npm --prefix services/webapp test

# check only, no rewrites: lint rules, formatting drift (fix with `ruff check --fix` / `ruff format` / `npm --prefix services/webapp exec prettier -- --write .`), types
lint:
	for s in $(SERVICES); do \
		uv run --directory services/$$s ruff check . && \
		uv run --directory services/$$s ruff format --check . && \
		uv run --directory services/$$s basedpyright || exit 1; \
	done
	npm --prefix services/webapp run lint

# the frontend's event types, generated from harness's OpenAPI: app.openapi() needs no server and no LLM env.
# npx, not a dependency: openapi-typescript wants typescript@^5 as a peer, the webapp is on 6
api-types:
	uv run --directory services/harness python -c "import json; from app.main import app; print(json.dumps(app.openapi()))" \
		| npx -y openapi-typescript@7.13.0 -o services/webapp/src/api/openapi.gen.ts
