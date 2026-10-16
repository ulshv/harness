import { describe, expect, it } from "vitest";
import { applyEvent, closeTurn, type AssistantTurn } from "./turn";

const streaming: AssistantTurn = { text: "", status: "streaming" };

describe("applyEvent", () => {
  it("appends text fragments", () => {
    const turn = applyEvent(applyEvent(streaming, { type: "text", text: "Hel" }), {
      type: "text",
      text: "lo",
    });

    expect(turn).toEqual({ text: "Hello", status: "streaming" });
  });

  it("ignores reasoning and tool events for now", () => {
    expect(applyEvent(streaming, { type: "reasoning", text: "Let me check." })).toBe(streaming);
    expect(
      applyEvent(streaming, { type: "tool_call", id: "c1", name: "wms_get_order", args: {} }),
    ).toBe(streaming);
    expect(
      applyEvent(streaming, {
        type: "tool_result",
        tool_call_id: "c1",
        name: "wms_get_order",
        content: "{}",
        status: "success",
      }),
    ).toBe(streaming);
  });

  it("ends the turn on done", () => {
    expect(applyEvent({ text: "Hi", status: "streaming" }, { type: "done" })).toEqual({
      text: "Hi",
      status: "done",
    });
  });

  it("keeps the text and records the message on error", () => {
    const turn = applyEvent(
      { text: "Partial", status: "streaming" },
      {
        type: "error",
        code: "llm_unavailable",
        message: "The model is unavailable.",
      },
    );

    expect(turn).toEqual({
      text: "Partial",
      status: "error",
      error: "The model is unavailable.",
    });
  });
});

describe("closeTurn", () => {
  it("marks a turn without done or error as cut off", () => {
    expect(closeTurn({ text: "Part", status: "streaming" })).toEqual({
      text: "Part",
      status: "error",
      error: "Connection lost",
    });
  });

  it("uses the given error", () => {
    expect(closeTurn(streaming, "Request failed (502)")).toEqual({
      text: "",
      status: "error",
      error: "Request failed (502)",
    });
  });

  it("leaves a finished turn alone", () => {
    const done: AssistantTurn = { text: "Hi", status: "done" };

    expect(closeTurn(done)).toBe(done);
  });
});
