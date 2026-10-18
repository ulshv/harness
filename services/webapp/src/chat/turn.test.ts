import { describe, expect, it } from "vitest";
import type { ChatEvent } from "../api/chat";
import { applyEvent, closeTurn, describeActivity, splitTurn, type AssistantTurn } from "./turn";

const streaming: AssistantTurn = { parts: [], status: "streaming" };

const fold = (events: ChatEvent[]) => events.reduce(applyEvent, streaming);

describe("applyEvent", () => {
  it("merges adjacent fragments of the same kind", () => {
    const turn = fold([
      { type: "reasoning", text: "Let me " },
      { type: "reasoning", text: "check." },
      { type: "text", text: "Hel" },
      { type: "text", text: "lo" },
    ]);

    expect(turn.parts).toEqual([
      { kind: "reasoning", text: "Let me check." },
      { kind: "text", text: "Hello" },
    ]);
  });

  it("pairs parallel tool calls with results that arrive in reverse order", () => {
    const turn = fold([
      { type: "tool_call", id: "c1", name: "wms_get_stock", args: { sku: "GLV-NIT-L" } },
      { type: "tool_call", id: "c2", name: "wms_get_stock", args: { sku: "TAPE-48" } },
      {
        type: "tool_result",
        tool_call_id: "c2",
        name: "wms_get_stock",
        content: "5",
        status: "error",
      },
      {
        type: "tool_result",
        tool_call_id: "c1",
        name: "wms_get_stock",
        content: "110",
        status: "success",
      },
    ]);

    expect(turn.parts).toEqual([
      {
        kind: "tool",
        id: "c1",
        name: "wms_get_stock",
        args: { sku: "GLV-NIT-L" },
        result: { content: "110", status: "success" },
      },
      {
        kind: "tool",
        id: "c2",
        name: "wms_get_stock",
        args: { sku: "TAPE-48" },
        result: { content: "5", status: "error" },
      },
    ]);
  });

  it("gives a result without a matching call its own part", () => {
    const turn = fold([
      { type: "tool_call", id: null, name: "current_time", args: {} },
      { type: "tool_result", tool_call_id: "c9", name: null, content: "late", status: "success" },
    ]);

    expect(turn.parts).toEqual([
      { kind: "tool", id: null, name: "current_time", args: {} },
      {
        kind: "tool",
        id: "c9",
        name: "",
        args: {},
        result: { content: "late", status: "success" },
      },
    ]);
  });

  it("pairs a result with the first unresolved call when an id repeats", () => {
    const turn = fold([
      { type: "tool_call", id: "a", name: "wms", args: { n: 1 } },
      { type: "tool_result", tool_call_id: "a", name: "wms", content: "1", status: "success" },
      { type: "tool_call", id: "a", name: "wms", args: { n: 2 } },
      { type: "tool_result", tool_call_id: "a", name: "wms", content: "2", status: "success" },
    ]);

    expect(turn.parts).toEqual([
      {
        kind: "tool",
        id: "a",
        name: "wms",
        args: { n: 1 },
        result: { content: "1", status: "success" },
      },
      {
        kind: "tool",
        id: "a",
        name: "wms",
        args: { n: 2 },
        result: { content: "2", status: "success" },
      },
    ]);
  });

  it("ignores an event type this build doesn't know", () => {
    const fromNewerHarness = { type: "todo", items: [] } as unknown as ChatEvent;

    expect(applyEvent(streaming, fromNewerHarness)).toBe(streaming);
  });

  it("ends the turn on done", () => {
    expect(applyEvent(streaming, { type: "done" })).toEqual({ parts: [], status: "done" });
  });

  it("keeps the parts and records the message on error", () => {
    const turn = fold([
      { type: "text", text: "Partial" },
      { type: "error", code: "llm_unavailable", message: "The model is unavailable." },
    ]);

    expect(turn).toEqual({
      parts: [{ kind: "text", text: "Partial" }],
      status: "error",
      error: "The model is unavailable.",
    });
  });
});

describe("splitTurn", () => {
  it("splits the measured order-1003 run into its steps and the answer", () => {
    const call = (id: string): ChatEvent => ({ type: "tool_call", id, name: "wms", args: {} });
    const result = (id: string): ChatEvent => ({
      type: "tool_result",
      tool_call_id: id,
      name: "wms",
      content: "{}",
      status: "success",
    });
    const turn = fold([
      { type: "reasoning", text: "Let me check order 1003." },
      { type: "text", text: "I'll check the order and its stock." },
      call("a"),
      result("a"),
      { type: "reasoning", text: "Check stock for both SKUs." },
      call("b"),
      call("c"),
      result("b"),
      result("c"),
      { type: "reasoning", text: "Tape is short." },
      { type: "text", text: "No — " },
      { type: "text", text: "TAPE-48 is short by 5." },
    ]);

    const { activity, answer } = splitTurn(turn.parts);

    expect(activity.map((p) => p.kind)).toEqual([
      "reasoning",
      "text",
      "tool",
      "reasoning",
      "tool",
      "tool",
      "reasoning",
    ]);
    expect(answer).toBe("No — TAPE-48 is short by 5.");
  });

  it("moves text into the activity once a tool call follows it", () => {
    const turn = fold([
      { type: "text", text: "I'll check." },
      { type: "tool_call", id: "a", name: "wms", args: {} },
    ]);

    expect(splitTurn(turn.parts)).toEqual({
      activity: [
        { kind: "text", text: "I'll check." },
        { kind: "tool", id: "a", name: "wms", args: {} },
      ],
      answer: "",
    });
  });

  it("doesn't start an answer on whitespace alone", () => {
    const parts = [
      { kind: "reasoning" as const, text: "Next, the stock." },
      { kind: "text" as const, text: "\n\n" },
    ];

    expect(splitTurn(parts)).toEqual({ activity: parts, answer: "" });
  });

  it("has no activity when the agent only answers", () => {
    expect(splitTurn([{ kind: "text", text: "Hi" }])).toEqual({ activity: [], answer: "Hi" });
  });
});

describe("describeActivity", () => {
  it("counts reasoning, tool calls and failures", () => {
    const tool = (status: "success" | "error") => ({
      kind: "tool" as const,
      id: null,
      name: "wms",
      args: {},
      result: { content: "", status },
    });

    expect(
      describeActivity([
        { kind: "reasoning", text: "…" },
        tool("success"),
        tool("error"),
        tool("success"),
      ]),
    ).toBe("Reasoning · 3 tool calls · 1 failed");
  });

  it("says one tool call in the singular and skips what didn't happen", () => {
    expect(describeActivity([{ kind: "tool", id: "a", name: "wms", args: {} }])).toBe(
      "1 tool call",
    );
  });
});

describe("closeTurn", () => {
  it("marks a turn without done or error as cut off", () => {
    const parts = [{ kind: "text" as const, text: "Part" }];

    expect(closeTurn({ parts, status: "streaming" })).toEqual({
      parts,
      status: "error",
      error: "Connection lost",
    });
  });

  it("uses the given error", () => {
    expect(closeTurn(streaming, "Request failed (502)")).toEqual({
      parts: [],
      status: "error",
      error: "Request failed (502)",
    });
  });

  it("leaves a finished turn alone", () => {
    const done: AssistantTurn = { parts: [], status: "done" };

    expect(closeTurn(done)).toBe(done);
  });
});
