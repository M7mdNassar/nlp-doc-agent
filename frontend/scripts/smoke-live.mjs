// Opt-in integration test: creates one synthetic document and makes one real LLM request.
// It deletes only its own document in cleanup, never any existing library content.
import { chromium, expect } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { randomUUID } from "node:crypto";

const baseURL = process.env.FRONTEND_URL || "http://localhost:3000";
const runId = randomUUID();
const filename = `Folio integration ${runId}.txt`;
const text = `Folio integration test ${runId}.\nIn a simulation-based evaluation, a traffic model improved throughput by approximately 0.25 cars per second compared with fixed timing. The report does not specify whether the input observations were real or synthetic.`;
const browser = await chromium.launch();
const context = await browser.newContext({
  baseURL,
  viewport: { width: 1440, height: 1000 },
  reducedMotion: "reduce",
});
const page = await context.newPage();
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
let documentId;
let removed = false;
await mkdir("test-results/live", { recursive: true });

try {
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "Connected", exact: true }),
  ).toBeVisible({ timeout: 30_000 });
  await page.screenshot({
    path: "test-results/live/01-workspace.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Upload documents", exact: true })
    .click();
  const uploadResponse = page.waitForResponse(
    (r) =>
      new URL(r.url()).pathname === "/api/backend/documents" &&
      r.request().method() === "POST",
  );
  await page
    .getByLabel("Choose files to upload")
    .setInputFiles({
      name: filename,
      mimeType: "text/plain",
      buffer: Buffer.from(text),
    });
  const uploaded = await uploadResponse;
  expect(uploaded.ok(), await uploaded.text()).toBe(true);
  const job = await uploaded.json();
  documentId = job.document_id;
  console.log(JSON.stringify({ step: "uploaded", ...job }));
  await expect(page.getByText("Ready for your questions")).toBeVisible({
    timeout: 180_000,
  });
  await page.getByRole("button", { name: "Close dialog" }).click();
  await page.getByRole("button", { name: /Document library/ }).click();
  await page.screenshot({
    path: "test-results/live/02-library.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: `Ask about ${filename}`, exact: true })
    .click();
  await page
    .getByRole("textbox", { name: "Ask a question about your documents" })
    .fill(
      "How was the traffic-throughput improvement evaluated, and what was the reported improvement?",
    );
  const answerResponse = page.waitForResponse(
    (r) => new URL(r.url()).pathname === "/api/backend/chat",
    { timeout: 600_000 },
  );
  await page.getByRole("button", { name: "Send message" }).click();
  const response = await answerResponse;
  expect(response.ok(), await response.text()).toBe(true);
  expect(response.request().postDataJSON().filters.doc_ids).toEqual([
    documentId,
  ]);
  const answer = await response.json();
  expect(answer.state).toBe("answer_ready");
  expect(answer.answer.toLowerCase()).toContain("simulation");
  expect(answer.answer).toContain("0.25");
  expect(answer.sources.length).toBeGreaterThan(0);
  expect(answer.sources.every((s) => s.document_id === documentId)).toBe(true);
  await expect(page.locator(".source-card").first()).toBeVisible();
  await page.screenshot({
    path: "test-results/live/03-answer.png",
    fullPage: true,
  });
  await page.locator(".source-card").first().click();
  await expect(page.locator(".source-quote")).toContainText("simulation-based");
  await page.screenshot({
    path: "test-results/live/04-source.png",
    fullPage: true,
  });
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  await page.screenshot({
    path: "test-results/live/05-dark.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/live/06-mobile.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole("button", { name: /Document library/ }).click();
  await page
    .getByRole("button", { name: `Delete ${filename}`, exact: true })
    .click();
  await page
    .getByRole("button", { name: "Remove document", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(
    page.locator(".document-row").filter({ hasText: filename }),
  ).toHaveCount(0);
  removed = true;
  expect(errors).toEqual([]);
  console.log(
    JSON.stringify({
      step: "passed",
      state: answer.state,
      sources: answer.sources.length,
      conversation_id: answer.conversation_id,
      cleaned_up: true,
      browser_errors: errors,
    }),
  );
} finally {
  if (documentId && !removed) {
    const cleanup = await context.request.delete(
      `/api/backend/documents/${encodeURIComponent(documentId)}`,
    );
    console.log(
      JSON.stringify({
        step: "cleanup",
        document_id: documentId,
        status: cleanup.status(),
      }),
    );
    if (!cleanup.ok())
      console.error(
        "The synthetic fixture remains in the library; remove it after processing completes:",
        filename,
      );
  }
  await browser.close();
}
