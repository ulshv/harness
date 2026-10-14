# 005. Spec: `reasoning` event

**Status:** implemented (2026-10-14)
**Implements in:** `docs/history/005.md`

## Problem

DeepSeek v4.1 flash thinks before it answers. A ~120-word answer took ~11.6 s to its first token, and the
client sees nothing during that time. The thinking is there, we just drop it:

- RouterAI (OpenRouter-style) streams it in `choices[0].delta.reasoning`, before any `content`. A raw
  stream for "17*23?" had 19 reasoning chunks, then one content chunk `"391"`.
- `ChatOpenAI` (langchain-openai 1.7.2) deliberately ignores non-standard fields (`reasoning`,
  `reasoning_content`, `reasoning_details`) on Chat Completions. Its module docstring points to provider
  packages instead.

## Goals

- Stream the model's reasoning as its own event, batched like text. The frontend shows it in a
  collapsible spoiler.
- Keep the translator provider-neutral, so it doesn't depend on which kwarg a provider uses.
- `/chat/invoke` returns the reasoning merged, the same way as text.
- No change to the error contract: the error table must keep working with the new model class.

## Non-goals

- Configuring reasoning (effort / on-off) per request or in settings.
- Sending reasoning back to the model. This already matters *within one turn*: in the ReAct loop the
  tool-calling `AIMessage` is re-sent on the next LLM call without its `reasoning_content` (neither
  `ChatOpenAI`'s message conversion nor `ChatDeepSeek` includes it). RouterAI accepts that, but the follow-up
  answer then comes without reasoning. Backlog item. *(Corrected after review: the first draft framed this as
  a multi-turn / memory concern only.)*
- `reasoning_details` / encrypted reasoning, signatures.
- The batching timer. Reasoning and text come from one continuous LLM stream, so the reasoning → text
  switch is an event change, not a pause. Re-measure live; the trigger stays in the backlog.

## API

New event, a member of the `ChatEvent` discriminated union:

| `type` / SSE event | `data` (SSE, without `type`) | Meaning |
|---|---|---|
| `reasoning` | `{"text": "<chunk of reasoning>"}` | the model's thinking; the frontend shows it in a spoiler |

```
event: reasoning
data: {"text":"We need to compute 17*23. 17*20=340, 17*3=51"}

event: reasoning
data: {"text":", total 391."}

event: text
data: {"text":"391"}

event: done
data: {}
```

`/chat/invoke`: `{"type": "reasoning", "text": "..."}` appears among the events, one per contiguous
reasoning block.

## Design

### Model: `ChatOpenAI` → `ChatDeepSeek`

`agent/llm.py` builds `ChatDeepSeek(model=..., base_url=..., api_key=...)` from `langchain-deepseek` 1.1.1
(`base_url` is the alias of its `api_base` field).
It is a `BaseChatOpenAI` subclass on the same `openai` SDK, and it lifts both `delta.reasoning_content`
(DeepSeek-native) and `delta.reasoning` (OpenRouter) into `additional_kwargs["reasoning_content"]`.

| Option | Verdict |
|---|---|
| `ChatOpenAI` | drops reasoning by policy |
| `ChatOpenRouter` (`langchain-openrouter` 0.2.9) | its `openrouter` SDK pins `pydantic<2.13`; we're on 2.14 |
| own `ChatOpenAI` subclass | would override a private chunk-conversion method and break on upgrades |
| **`ChatDeepSeek`** | handles RouterAI's format today. The class name is DeepSeek-specific, but it parses the generic OpenRouter field, so other RouterAI models with normalized `reasoning` work too |

`LLM_*` settings don't change. Because the class is still `BaseChatOpenAI`, provider errors stay
`langchain_core.exceptions.Model*Error` subclasses. This is verified live with a wrong key (`internal`, as before).

### Translator: content blocks instead of `.text`

In `stream.py`, `_from_tokens` reads `msg.content_blocks`, langchain-core's standard view of a message.
It turns `additional_kwargs["reasoning_content"]` into `{"type": "reasoning", "reasoning": ...}` and text
into `{"type": "text", "text": ...}`. A flat table maps block type to event; other block types (for example
`tool_call_chunk`) are skipped:

```python
_BY_BLOCK = {
    "text": lambda block: TextEvent(text=block["text"]),
    "reasoning": lambda block: ReasoningEvent(text=block["reasoning"]),
}
```

Empty strings are skipped, as today. `reasoning` is `NotRequired` in langchain-core's block type (a
signature-only block has no text), so it's read with `.get`. Anthropic's thinking or other providers' reasoning would arrive as
the same `reasoning` block, so the translator doesn't change when the provider does.

### Batching: `batch_text_events` → `batch_events`

Reasoning is even chattier than text, so it is batched the same way. The rule generalizes from "adjacent
`TextEvent`s" to "adjacent events of the **same mergeable kind**" (`TextEvent`, `ReasoningEvent`). A
change of kind (reasoning → text) flushes the buffer like any other event. Everything else passes
through. The window, the edge windows (`0` / `inf`) and the "no timer" trade-off are unchanged.

## Code changes

| File | Change |
|---|---|
| `pyproject.toml` / `uv.lock` | `langchain-deepseek==1.1.1`; the direct `langchain-openai` dependency is dropped, since nothing imports it now (still locked at 1.7.2 as a transitive dependency) *(during implementation)* |
| `app/agent/llm.py` | `ChatDeepSeek` instead of `ChatOpenAI` |
| `app/api/chat/schemas.py` | `ReasoningEvent`; added to `ChatEvent` |
| `app/api/chat/stream.py` | `_from_tokens` dispatches on `content_blocks` |
| `app/api/chat/batching.py` | `batch_text_events` → `batch_events`; merges same-kind text/reasoning runs |
| `app/api/chat/chat.py` | uses `batch_events` |
| `tests/conftest.py` | `StreamingFakeModel` can stream reasoning chunks before text |
| `CLAUDE.md` | pinned versions: `langchain-deepseek` |
| `docs/arch/001_chat-request-flow.md` | updated in place |
| `docs/ROADMAP.md` | remove "reasoning" from next up |
| `docs/history/005.md` | step log |

## Tests

Expected values are literals.

- `test_stream.py`: a chunk with `additional_kwargs={"reasoning_content": "We"}` gives
  `ReasoningEvent(text="We")`; a text chunk gives `TextEvent`; a chunk with neither gives nothing.
- `test_batching.py`: `window=inf` turns `[R a, R b, T c, T d, ToolCall, T e]` into `[R ab, T cd, ToolCall, T e]`;
  the `window=0` and time-window tests carry over to `batch_events`.
- `test_chat.py`: a streaming fake with reasoning `["Let", " me"]` then text `["Hi"]` gives SSE
  `reasoning {"text":"Let me"}`, `text {"text":"Hi"}`, `done`. `/chat/invoke` gives the same three as JSON
  with `type`. OpenAPI mapping includes `reasoning`.

## How to verify

```bash
make test && make lint
Q='{"message":"What is 17*23? Answer with just the number."}'
curl -sN localhost:8000/chat/stream -H 'content-type: application/json' -d "$Q"
# event: reasoning … (several frames, starting within ~1 s instead of ~11 s of silence)
# event: text / data: {"text":"391"}
# event: done
curl -s localhost:8000/chat/invoke -H 'content-type: application/json' -d "$Q" | jq '.events[] | .type'
# "reasoning" "text" "done"
```

Also measure: time to the first frame, and reasoning frames before vs after batching.

## Decisions

| Question | Decision | Why |
|---|---|---|
| Model class | `ChatDeepSeek` | parses RouterAI's `delta.reasoning`; same `openai` SDK and error wrappers; the alternatives are blocked or fragile |
| Where reasoning is read | `content_blocks` | langchain-core's provider-neutral view; the translator doesn't know provider kwargs |
| Event shape | `reasoning` with `{"text"}` | mirrors `text`; the client shows it in a spoiler |
| Batching function name | `batch_events` | it now merges text and reasoning runs; other events pass through |
| Reasoning in `/invoke` | merged, like text | `/invoke` stays the merged stream |
