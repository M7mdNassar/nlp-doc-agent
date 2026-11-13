import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import type { Answer, DocumentItem, ProgressStep } from "../src/lib/models";

const source = {
  chunk_id: "chunk_report",
  document_id: "doc_report",
  document_name: "Research report.pdf",
  page: 4,
  section: null,
  location: null,
  quote:
    "Traffic throughput improved by approximately 0.25 cars/s compared with fixed timing (simulation-based).",
};
const documents: DocumentItem[] = [
  { id: "doc_report", name: "Research report.pdf", status: "indexed" },
  { id: "doc_notes", name: "Experiment notes.md", status: "indexed" },
];
const answer: Answer = {
  answer:
    "Throughput improved by approximately **0.25 cars/s** compared with fixed timing **in simulation**.\n\n[Research report.pdf, p. 4]\n\nSources:\n- Research report.pdf, p. 4 (chunk_report)",
  state: "answer_ready",
  loops: 0,
  evidence_count: 2,
  sources: [source],
  tool_results: [],
  conversation_id: "conv_browser_test",
};

for (const [status, label] of [
  ["miss", "Cache miss"],
  ["exact_hit", "Cache hit · Exact"],
  ["semantic_hit", "Cache hit · Semantic"],
  ["bypass", "Cache bypassed"],
] as const) {
  test(`shows and persists ${status} with cached sources`, async ({ page }) => {
    const api = await mockApi(page);
    api.setChat({
      ...answer,
      cache: {
        status,
        age_seconds: 4,
        similarity: status === "semantic_hit" ? 0.99 : null,
      },
    });
    await page.goto("/");
    await page
      .getByRole("textbox", { name: "Ask a question about your documents" })
      .fill("Explain the result.");
    await page.getByRole("button", { name: "Send message" }).click();
    await expect(page.getByText(label, { exact: true })).toBeVisible();
    await page.reload();
    await expect(page.getByText(label, { exact: true })).toBeVisible();
    await expect(page.getByText("Research report.pdf").first()).toBeVisible();
  });
}

async function mockApi(page: Page, initial: DocumentItem[] = documents) {
  let items = [...initial];
  const chats: Record<string, unknown>[] = [];
  const removed: string[] = [];
  let jobReads = 0;
  let chatStatus = 200;
  let result: unknown = answer;
  let delay = 0;
  await page.route("**/api/backend/**", async (route) => {
    const path = new URL(route.request().url()).pathname.replace(
      "/api/backend/",
      "",
    );
    const method = route.request().method();
    if (path === "health")
      return route.fulfill({
        json: {
          status: "ok",
          dependencies: { sqlite: "ok", qdrant: "ok", redis: "ok" },
        },
      });
    if (path === "documents" && method === "GET")
      return route.fulfill({ json: { items } });
    if (path === "chat" || path === "chat/stream") {
      chats.push(route.request().postDataJSON());
      if (delay) await new Promise((resolve) => setTimeout(resolve, delay));
      return route
        .fulfill({ status: chatStatus, json: result })
        .catch(() => {});
    }
    if (path === "documents" && method === "POST") {
      items.push({ id: "doc_new", name: "Test notes.txt", status: "queued" });
      return route.fulfill({
        json: { document_id: "doc_new", job_id: "job_new", status: "queued" },
      });
    }
    if (path === "jobs/job_new") {
      jobReads++;
      const completed = jobReads >= 2;
      if (completed)
        items = items.map((d) =>
          d.id === "doc_new" ? { ...d, status: "indexed" } : d,
        );
      return route.fulfill({
        json: {
          document_id: "doc_new",
          job_id: "job_new",
          status: completed ? "completed" : "processing",
          error: null,
        },
      });
    }
    if (method === "DELETE") {
      const id = path.split("/")[1];
      removed.push(id);
      items = items.filter((d) => d.id !== id);
      return route.fulfill({ json: { status: "deleted" } });
    }
    if (path.endsWith("/reindex")) {
      return route.fulfill({
        status: 503,
        json: {
          code: "QUEUE_UNAVAILABLE",
          message:
            "Could not enqueue ingestion. Check Redis and retry reindexing.",
        },
      });
    }
    return route.fulfill({ status: 404, json: { message: "Not found" } });
  });
  return {
    chats,
    removed,
    setChat: (value: unknown, status = 200) => {
      result = value;
      chatStatus = status;
    },
    setDelay: (value: number) => {
      delay = value;
    },
    setDocuments: (value: DocumentItem[]) => {
      items = value;
    },
  };
}

test("agent flow follows live events, repeats retrieval, and saves tools after completion", async ({
  page,
}, testInfo) => {
  await mockApi(page);
  await page.addInitScript(() => {
    const original = window.fetch;
    window.fetch = async (input, init) => {
      if (!String(input).endsWith("/api/backend/chat/stream"))
        return original(input, init);
      let receive: EventListener;
      const body = new ReadableStream<Uint8Array>({
        start(controller) {
          receive = (event) => {
            const data = (event as CustomEvent).detail;
            controller.enqueue(
              new TextEncoder().encode(`data: ${JSON.stringify(data)}\n\n`),
            );
            if (data.type === "result" || data.type === "error") {
              window.removeEventListener("test-agent-event", receive);
              controller.close();
            }
          };
          window.addEventListener("test-agent-event", receive);
          init?.signal?.addEventListener(
            "abort",
            () => {
              window.removeEventListener("test-agent-event", receive);
              controller.error(new DOMException("Aborted", "AbortError"));
            },
            { once: true },
          );
        },
        cancel() {
          window.removeEventListener("test-agent-event", receive);
        },
      });
      return new Response(body, {
        headers: { "content-type": "text/event-stream" },
      });
    };
  });
  await page.goto("/");
  await page
    .getByRole("textbox", { name: "Ask a question about your documents" })
    .fill("Compare the reported results.");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(
    page.getByRole("region", { name: "Processing your question" }),
  ).toBeVisible();
  const activity: ProgressStep[] = [];
  async function step(value: ProgressStep) {
    const index = activity.findIndex((item) => item.id === value.id);
    if (index >= 0) activity[index] = value;
    else activity.push(value);
    await page.evaluate(
      (detail) =>
        window.dispatchEvent(new CustomEvent("test-agent-event", { detail })),
      { type: "progress", step: value },
    );
  }
  const retrieval: ProgressStep = {
    id: "step_1",
    agent: "retriever",
    label: "Finding relevant passages",
    kind: "agent",
    status: "running",
    tool: null,
  };
  await step(retrieval);
  await expect(
    page.locator('.agent-stages [aria-current="step"]'),
  ).toContainText("Retriever");
  await expect(page.locator(".prose")).toHaveCount(0);
  await page.screenshot({
    path: testInfo.outputPath("agent-flow-desktop.png"),
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator(".agent-stages")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("agent-flow-mobile.png") });
  const accessibility = await new AxeBuilder({ page })
    .include(".processing-card")
    .analyze();
  expect(accessibility.violations).toEqual([]);
  await step({ ...retrieval, status: "completed" });
  const analysis: ProgressStep = {
    id: "step_2",
    agent: "analyst",
    label: "Assessing the evidence",
    kind: "agent",
    status: "running",
    tool: null,
  };
  await step(analysis);
  const calculator: ProgressStep = {
    id: "step_3",
    agent: "analyst",
    label: "Calculator",
    kind: "tool",
    status: "running",
    tool: "calculator",
  };
  await step(calculator);
  await expect(page.locator(".agent-current")).toHaveText("Calculator");
  await step({ ...calculator, status: "completed" });
  await step({ ...analysis, status: "completed" });
  await step({ ...retrieval, id: "step_4" });
  await expect(
    page.locator('.agent-stages [aria-current="step"]'),
  ).toContainText("Retriever");
  await step({ ...retrieval, id: "step_4", status: "completed" });
  await step({
    id: "step_5",
    agent: "answer",
    label: "Writing the answer",
    kind: "agent",
    status: "completed",
    tool: null,
  });
  const review: ProgressStep = {
    id: "step_6",
    agent: "verification",
    label: "Reviewing answer grounding",
    kind: "agent",
    status: "running",
    tool: null,
  };
  await step(review);
  await expect(
    page.locator('.agent-stages [aria-current="step"]'),
  ).toContainText("Verification");
  await expect(page.locator(".prose")).toHaveCount(0);
  await step({ ...review, status: "completed" });
  const completed: Answer = {
    ...answer,
    activity,
    tools_used: [
      {
        name: "calculator",
        label: "Calculator",
        agent: "analyst",
        calls: 1,
        completed: 1,
        failed: 0,
      },
    ],
    tool_results: [
      {
        name: "calculator",
        output: { result: 4 },
        chunk_ids: [source.chunk_id],
      },
    ],
  };
  await page.evaluate(
    (detail) =>
      window.dispatchEvent(new CustomEvent("test-agent-event", { detail })),
    { type: "result", result: completed },
  );
  await expect(page.locator(".processing-card")).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Tools used" })).toContainText(
    "Calculator",
  );
  await page.getByText("View analysis results", { exact: true }).click();
  await expect(page.locator(".tool-details")).toContainText("Result: 4");
  await page.screenshot({ path: testInfo.outputPath("tools-used-mobile.png") });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({
    path: testInfo.outputPath("tools-used-desktop.png"),
  });
  await page.reload();
  await expect(page.getByRole("region", { name: "Tools used" })).toContainText(
    "Calculator",
  );
  await page.getByText("Agent activity", { exact: false }).click();
  await expect(page.locator(".activity-history li")).toHaveCount(6);
});

test("empty workspace uploads, polls processing, and makes the source available", async ({
  page,
}) => {
  await mockApi(page, []);
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: /Your documents/ }),
  ).toBeVisible();
  await page
    .getByRole("textbox", { name: "Ask a question about your documents" })
    .fill("What matters here?");
  await expect(
    page.getByRole("button", { name: "Send message" }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: /Make room for your next idea/ })
    .click();
  await page.getByLabel("Choose files to upload").setInputFiles({
    name: "Test notes.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("Synthetic research notes for testing."),
  });
  await expect(page.getByText("Ready for your questions")).toBeVisible();
  await page.getByRole("button", { name: "Close dialog" }).click();
  await expect(
    page.getByRole("button", { name: "Send message" }),
  ).toBeEnabled();
});

test("answers cite exact excerpts, preserve follow-up IDs, and persist after reload", async ({
  page,
}) => {
  const api = await mockApi(page);
  await page.goto("/");
  await page
    .getByRole("textbox", { name: "Ask a question about your documents" })
    .fill("What improved?");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.locator(".prose")).toContainText("in simulation");
  await page.locator(".inline-citation").click();
  await expect(page.getByRole("dialog")).toContainText(source.quote);
  await expect(page.getByRole("dialog")).toContainText("Page 4");
  await page.keyboard.press("Escape");
  await page
    .getByRole("textbox", { name: "Ask a question about your documents" })
    .fill("What was the baseline?");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.locator(".answer-message")).toHaveCount(2);
  expect(api.chats[1].conversation_id).toBe("conv_browser_test");
  await page.reload();
  await expect(page.locator(".answer-message")).toHaveCount(2);
  await page.getByRole("button", { name: "Download conversation" }).click();
});

test("explicit source selection and an empty selection never widen the request", async ({
  page,
}) => {
  const api = await mockApi(page);
  await page.goto("/");
  await page
    .getByRole("button", { name: "All documents", exact: true })
    .click();
  await page.getByRole("checkbox", { name: /All ready documents/ }).uncheck();
  await page.getByRole("button", { name: "Apply selection" }).click();
  await page
    .getByRole("textbox", { name: "Ask a question about your documents" })
    .fill("Summarize");
  await expect(
    page.getByRole("button", { name: "Send message" }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "Choose sources", exact: true })
    .click();
  await page.getByRole("checkbox", { name: /Research report.pdf/ }).check();
  await page.getByRole("button", { name: "Apply selection" }).click();
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.locator(".answer-message")).toHaveCount(1);
  expect(api.chats[0].filters).toEqual({ doc_ids: ["doc_report"] });
});

test("unavailable selected sources block requests instead of searching everything", async ({
  page,
}) => {
  const api = await mockApi(page);
  await page.goto("/");
  await page.getByRole("button", { name: /Document library/ }).click();
  await page
    .getByRole("button", { name: "Ask about Research report.pdf" })
    .click();
  api.setDocuments([documents[1]]);
  await page.reload();
  await expect(
    page.getByText(/Some selected documents aren’t ready/),
  ).toBeVisible();
  await page
    .getByRole("textbox", { name: "Ask a question about your documents" })
    .fill("Question");
  await expect(
    page.getByRole("button", { name: "Send message" }),
  ).toBeDisabled();
});

test("deletion requires confirmation and reindex failures are visible", async ({
  page,
}) => {
  const api = await mockApi(page);
  await page.goto("/");
  await page.getByRole("button", { name: /Document library/ }).click();
  await page
    .getByRole("button", { name: "Reindex Research report.pdf" })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "Could not enqueue ingestion",
  );
  await page
    .getByRole("button", { name: "Delete Research report.pdf" })
    .click();
  expect(api.removed).toHaveLength(0);
  await page.getByRole("button", { name: "Keep document" }).click();
  expect(api.removed).toHaveLength(0);
  await page
    .getByRole("button", { name: "Delete Research report.pdf" })
    .click();
  await page
    .getByRole("button", { name: "Remove document", exact: true })
    .click();
  await expect(page.locator(".document-row")).toHaveCount(1);
  expect(api.removed).toEqual(["doc_report"]);
});

test("invalid uploads are rejected without an API upload", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  let uploads = 0;
  page.on("request", (request) => {
    if (request.url().endsWith("/documents") && request.method() === "POST")
      uploads++;
  });
  await page
    .getByRole("button", { name: "Upload documents", exact: true })
    .click();
  await page.getByLabel("Choose files to upload").setInputFiles([
    {
      name: "script.exe",
      mimeType: "application/octet-stream",
      buffer: Buffer.from("bad"),
    },
    { name: "empty.txt", mimeType: "text/plain", buffer: Buffer.from("") },
  ]);
  await expect(
    page.getByText("This file is empty. Choose a file with content."),
  ).toBeVisible();
  await expect(
    page.getByText("Choose a PDF, Word (.docx), text, or Markdown file."),
  ).toBeVisible();
  expect(uploads).toBe(0);
});

test("insufficient evidence stays explicit and does not invent citations", async ({
  page,
}) => {
  const api = await mockApi(page);
  api.setChat({
    ...answer,
    answer: "I don't have enough verified evidence to answer.",
    state: "insufficient_evidence",
    sources: [],
  });
  await page.goto("/");
  await page
    .getByRole("textbox", { name: "Ask a question about your documents" })
    .fill("Unknown salary?");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(
    page.getByText("Not enough verified evidence", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".source-card")).toHaveCount(0);
});

test("provider errors allow retry, and cancellation does not fabricate an answer", async ({
  page,
}) => {
  const api = await mockApi(page);
  api.setChat({ message: "Rate limited" }, 429);
  await page.goto("/");
  await page
    .getByRole("textbox", { name: "Ask a question about your documents" })
    .fill("Question");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.locator(".answer-error[role=alert]")).toContainText(
    "usage limit",
  );
  api.setChat(answer);
  api.setDelay(3000);
  await page.getByRole("button", { name: "Try again", exact: true }).click();
  await page.getByRole("button", { name: "Stop waiting", exact: true }).click();
  await expect(
    page.getByText(/You stopped waiting for this answer/),
  ).toBeVisible();
  await expect(page.locator(".source-card")).toHaveCount(0);
});

test("Groq quota failures show the wait time instead of insufficient evidence and can recover", async ({
  page,
}) => {
  const api = await mockApi(page);
  api.setChat(
    {
      code: "LLM_RATE_LIMITED",
      message:
        "Groq has reached a request or token limit. Please try again later.",
      details: { provider: "Groq", retry_after_seconds: 879 },
    },
    429,
  );
  await page.goto("/");
  await page
    .getByRole("textbox", { name: "Ask a question about your documents" })
    .fill("Tell me about Nafe's projects");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.locator(".answer-error")).toContainText(
    "Groq has reached a request or token limit",
  );
  await expect(page.locator(".answer-error")).toContainText("15 minutes");
  await expect(page.locator(".answer-error")).toContainText(
    "Your documents are still available",
  );
  await expect(page.locator(".evidence-notice")).toHaveCount(0);
  await expect(page.locator(".source-card")).toHaveCount(0);
  expect(api.chats).toHaveLength(1);
  api.setChat(answer);
  await page.getByRole("button", { name: "Try again", exact: true }).click();
  await expect(page.locator(".source-card")).toHaveCount(1);
  expect(api.chats[1].message).toBe("Tell me about Nafe's projects");
});

test("source and model content cannot execute HTML or JavaScript", async ({
  page,
}) => {
  const api = await mockApi(page);
  api.setChat({
    ...answer,
    answer:
      '<script>window.pwned = true</script>\n\n[unsafe](javascript:alert(1))\n\n<img src=x onerror="window.pwned=true">\n\n![tracking image](https://tracker.invalid/pixel)',
    sources: [{ ...source, quote: '<img src=x onerror="window.pwned=true">' }],
  });
  await page.goto("/");
  await page
    .getByRole("textbox", { name: "Ask a question about your documents" })
    .fill("Show result");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.locator(".source-card")).toHaveCount(1);
  expect(await page.evaluate(() => "pwned" in window)).toBe(false);
  await expect(page.locator('.prose a[href^="javascript:"]')).toHaveCount(0);
  await expect(page.locator(".prose img")).toHaveCount(0);
  await page.locator(".source-card").click();
  await expect(page.locator(".source-quote img")).toHaveCount(0);
});

test("backend outage is recoverable", async ({ page }) => {
  await mockApi(page);
  await page.route("**/api/backend/documents", (route) =>
    route.fulfill({
      status: 502,
      json: { message: "We couldn’t reach the backend." },
    }),
  );
  await page.goto("/");
  await expect(page.locator(".workspace-banner[role=alert]")).toContainText(
    "couldn’t reach",
  );
  await page.unroute("**/api/backend/documents");
  await page.getByRole("button", { name: "Reconnect" }).click();
  await expect(page.locator(".workspace-banner[role=alert]")).toHaveCount(0);
});

test("light and dark workspace and dialogs meet automated accessibility checks", async ({
  page,
}) => {
  await mockApi(page);
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "Connected", exact: true }),
  ).toBeVisible();
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page
    .getByRole("button", { name: "Upload documents", exact: true })
    .click();
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("mobile layout has no horizontal overflow and supports navigation", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page);
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: /Your documents/ }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("button", { name: /Document library/ }).click();
  await expect(
    page.getByRole("heading", { name: /The document library/ }),
  ).toBeVisible();
  await page.getByRole("textbox", { name: "Search documents" }).fill("notes");
  await expect(page.locator(".document-row")).toHaveCount(1);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

test("library, answer, source drawer, and source picker remain accessible", async ({
  page,
}) => {
  await mockApi(page, [
    ...documents,
    { id: "doc_failed", name: "Scan.docx", status: "failed" },
    { id: "doc_processing", name: "Processing.txt", status: "embedding" },
  ]);
  await page.goto("/");
  async function check() {
    // Measure the settled layout instead of a transient fade-in frame.
    await page.evaluate(async () => {
      await Promise.all(
        document
          .getAnimations()
          .filter(
            (animation) =>
              animation.effect?.getTiming().iterations !== Infinity,
          )
          .map((animation) => animation.finished.catch(() => {})),
      );
    });
    const result = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    expect(
      result.violations.map((v) => ({
        id: v.id,
        nodes: v.nodes.map((n) => ({
          target: n.target,
          reason: n.failureSummary,
        })),
      })),
    ).toEqual([]);
  }
  await page.getByRole("button", { name: /Document library/ }).click();
  await expect(page.locator(".document-row")).toHaveCount(4);
  await check();
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  await check();
  await page
    .getByRole("button", { name: "Ask about Research report.pdf" })
    .click();
  await page
    .getByRole("textbox", { name: "Ask a question about your documents" })
    .fill("What improved?");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.locator(".source-card")).toHaveCount(1);
  await check();
  await page.locator(".inline-citation").click();
  await check();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Switch to light theme" }).click();
  await check();
  await page.locator(".inline-citation").click();
  await check();
  await page.keyboard.press("Escape");
  await page.locator(".scope-picker").click();
  await check();
});
