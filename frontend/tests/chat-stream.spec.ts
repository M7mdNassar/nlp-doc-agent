import { test, expect } from "@playwright/test";
import { readChatStream } from "../src/lib/api";
import type { ProgressStep } from "../src/lib/models";

const step: ProgressStep = {
  id: "step_1",
  agent: "analyst",
  label: "Assessing evidence…",
  kind: "agent",
  status: "running",
  tool: null,
};
const answer = {
  answer: "Verified answer",
  state: "answer_ready",
  loops: 0,
  evidence_count: 1,
  sources: [],
  tool_results: [],
  conversation_id: "c1",
};
const encode = (value: unknown) =>
  new TextEncoder().encode(`data: ${JSON.stringify(value)}\r\n\r\n`);

test("stream parser delivers progress before the final answer and handles fragmented UTF-8", async () => {
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const body = new ReadableStream<Uint8Array>({
    start(value) {
      controller = value;
    },
  });
  const received: ProgressStep[] = [];
  const pending = readChatStream(
    new Response(body, { headers: { "content-type": "text/event-stream" } }),
    (value) => received.push(value),
  );
  const bytes = encode({ type: "progress", step });
  for (const byte of bytes) controller.enqueue(new Uint8Array([byte]));
  await expect.poll(() => received.length).toBe(1);
  expect(received[0].label).toBe("Assessing evidence…");
  controller.enqueue(encode({ type: "result", result: answer }));
  controller.close();
  expect((await pending).answer).toBe("Verified answer");
});

test("stream errors preserve rate-limit guidance and unfinished streams never become answers", async () => {
  const response = new Response(
    encode({
      type: "error",
      error: {
        status: 429,
        code: "LLM_RATE_LIMITED",
        message: "Provider usage limit.",
        details: { retry_after_seconds: 45 },
      },
    }),
    { headers: { "content-type": "text/event-stream" } },
  );
  await expect(readChatStream(response, () => {})).rejects.toThrow(
    "45 seconds",
  );
  for (const body of [
    ": keep-alive\n\n",
    "data: invalid\n\n",
    'data: {"type":"result","result":{}}\n\n',
  ]) {
    await expect(
      readChatStream(
        new Response(body, {
          headers: { "content-type": "text/event-stream" },
        }),
        () => {},
      ),
    ).rejects.toThrow();
  }
});
