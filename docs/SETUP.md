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
uv sync                 # .venv with the dev group (pytest, ruff, httpx2)
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
```

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

Source: `docs/imgs/architecture.mmd`, which is also copied into the Mermaid spoilers of `README.md` and
`README-ru.md`; keep all three in sync (the diagram itself stays in English).
The SVG is rendered with `mermaid-cli` and a local Chrome. Labels must be plain SVG text: with the default HTML labels
(`<foreignObject>`), viewers that don't render HTML inside SVG (image viewers, librsvg, …) show empty boxes.
In mermaid-cli 12, `htmlLabels` has to be set at the **root** of the config; `flowchart.htmlLabels` alone is ignored.
A monospace stack is set explicitly: mermaid measures label widths with the render-time font, and mono fonts
have near-identical widths (~0.6 em) across platforms. `wrappingWidth: 400` stops auto-wrapping, so lines
break only at the `<br/>` in the source. Keep labels short: the README shows the SVG at ~880 px. The diagram is a `flowchart` laid out by dagre *from its edges*: describe the real
relationships and let layers emerge from the flow; don't try to force rows inside subgraphs (dagre ignores or
inverts nested `direction`). Node declaration order nudges left-to-right placement within a layer. Check with
`grep -o '<foreignObject' docs/imgs/architecture.svg | wc -l`, which must print `0`.

```bash
echo '{"executablePath":"/usr/bin/google-chrome","args":["--no-sandbox"]}' > /tmp/puppeteer.json
F='ui-monospace, SFMono-Regular, Menlo, Consolas, DejaVu Sans Mono, Liberation Mono, monospace'
echo "{\"htmlLabels\":false,\"fontFamily\":\"$F\",\"themeVariables\":{\"fontFamily\":\"$F\",\"fontSize\":\"16px\"},\"flowchart\":{\"htmlLabels\":false,\"wrappingWidth\":400}}" > /tmp/mermaid.json
PUPPETEER_SKIP_DOWNLOAD=1 npx -y @mermaid-js/mermaid-cli@12.0.0 -p /tmp/puppeteer.json -c /tmp/mermaid.json \
  -i docs/imgs/architecture.mmd -o docs/imgs/architecture.svg -b white
```
