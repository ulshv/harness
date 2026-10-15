# Environment setup

## Step 0 (2026-10-14)

Everything was already on the host, nothing to install:

| Tool | Version | Why |
|---|---|---|
| docker / compose | 29.5.3 / v5.1.4 | containers and `up --watch` (needs compose ≥ 2.22) |
| uv | 0.11.22 | Python dependencies and the lock file |
| go | 1.26.2 | auth service (step 5) |
| node / npm | 22.22.3 / 10.9.8 | web (step 2) |
| python3 | 3.14.4 | local venv for tests; the container has its own 3.14.8 |

Check:

```bash
docker compose version && uv --version && go version && node --version
```

### Local dev for harness

```bash
cd services/harness
uv sync                 # .venv with the dev group (pytest, ruff, basedpyright, httpx2)
uv run pytest -q
uv run ruff check . && uv run ruff format --check . && uv run basedpyright
```

### MCP Inspector

The official UI for poking an MCP server: lists its tools with descriptions and calls them by hand. Needs Node.

```bash
npx @modelcontextprotocol/inspector   # transport "Streamable HTTP", URL http://localhost:8101/mcp
```

It runs in proxy mode by default: the browser talks to a local proxy, and the proxy calls the server, so the
server's Host/Origin allowlist (`localhost:*`) is enough.

### Library references

Sources at pinned tags in `.reference/` (gitignored), shallow clones:

```bash
mkdir -p .reference && cd .reference
git clone --depth 1 --branch 1.2.15 https://github.com/langchain-ai/langgraph
git clone --depth 1 --branch deepagents==0.7.25 https://github.com/langchain-ai/deepagents
git clone --depth 1 --branch langchain==1.4.5 https://github.com/langchain-ai/langchain
git clone --depth 1 --branch langchain-mcp-adapters==0.3.2 https://github.com/langchain-ai/langchain-mcp-adapters
git clone --depth 1 --branch 0.143.1 https://github.com/fastapi/fastapi
```

langchain-ai monorepos tag as `pkg==X.Y.Z`, langgraph as plain `X.Y.Z`.

## Step 1 (2026-10-14): LLM key

```bash
cp .env.example .env    # gitignored
# put the RouterAI key into LLM_API_KEY (routerai.ru → settings → API keys)
```

Model list (OpenRouter-style API, ids are `vendor/model`):

```bash
curl -s https://routerai.ru/api/v1/models | jq -r '.data[].id' | grep deepseek
```

## Architecture diagram (README)

`docs/imgs/architecture.svg` is **hand-drawn**: explicit coordinates, orthogonal edges, plain SVG `<text>`
(no `<foreignObject>`, so it renders in any viewer), and a monospace font stack. Edit it directly, and check the
result in a browser inside an `<img>` at ~880 px wide, which is how GitHub shows it.

`docs/imgs/architecture.mmd` is the Mermaid version of the same diagram, copied into the spoilers of `README.md` and
`README-ru.md` (GitHub renders it natively). It isn't the SVG's source. Keep the SVG, the `.mmd` and both README
copies in sync by meaning when components change.

Why not `mermaid-cli`: its dagre layout can't keep layers tidy as the diagram grows, and the default HTML labels
(`<foreignObject>`) show up as empty boxes outside browsers.
