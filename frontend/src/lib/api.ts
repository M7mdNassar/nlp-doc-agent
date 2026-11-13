import { z } from "zod";
import {
  answerSchema,
  chatEventSchema,
  documentListSchema,
  healthSchema,
  jobSchema,
  type Answer,
  type ProgressStep,
} from "./models";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code?: string,
  ) {
    super(message);
  }
}
async function request<T>(
  path: string,
  schema: z.ZodType<T>,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`/api/backend/${path}`, {
    ...init,
    cache: "no-store",
  });
  return parseResponse(response, schema);
}

async function parseResponse<T>(
  response: Response,
  schema: z.ZodType<T>,
): Promise<T> {
  let data;
  try {
    data = await response.json();
  } catch {
    throw new ApiError(
      "The service returned an unreadable response. Please try again.",
      response.status,
    );
  }
  if (!response.ok) {
    let message =
      data.message || (typeof data.detail === "string" ? data.detail : null);
    if (!message && Array.isArray(data.detail))
      message = data.detail
        .map((item: { msg?: string }) => item.msg)
        .filter(Boolean)
        .join(" ");
    if (response.status === 429) {
      if (data.code === "LLM_RATE_LIMITED") {
        const seconds = Number(
          data.details?.retry_after_seconds ??
            response.headers.get("retry-after"),
        );
        const wait =
          Number.isFinite(seconds) && seconds > 0
            ? seconds >= 60
              ? `Please wait about ${Math.ceil(seconds / 60)} minute${seconds > 60 ? "s" : ""} before trying again.`
              : `Please wait about ${Math.ceil(seconds)} second${seconds > 1 ? "s" : ""} before trying again.`
            : "Please try again after the provider limit resets.";
        message = `${message || "The AI provider has reached a usage limit."} ${wait} Your documents are still available.`;
      } else {
        message =
          "The service has reached a usage limit. Please try again later.";
      }
    }
    throw new ApiError(
      message || "Something went wrong. Please try again.",
      response.status,
      data.code,
    );
  }
  const parsed = schema.safeParse(data);
  if (!parsed.success)
    throw new ApiError(
      "The service returned an unexpected response. Refresh and try again.",
      502,
    );
  return parsed.data;
}

export async function readChatStream(
  response: Response,
  onProgress: (step: ProgressStep) => void,
): Promise<Answer> {
  if (
    !response.ok ||
    !response.headers.get("content-type")?.includes("text/event-stream")
  )
    return parseResponse(response, answerSchema);
  if (!response.body)
    throw new ApiError("The response stream was empty. Please try again.", 502);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      buffer = buffer.replaceAll("\r\n", "\n");
      if (buffer.length > 2_000_000)
        throw new ApiError("The response stream was too large.", 502);
      let boundary;
      while ((boundary = buffer.indexOf("\n\n")) >= 0) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const data = frame
          .split("\n")
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).trimStart())
          .join("\n");
        if (!data) continue;
        let raw: unknown;
        try {
          raw = JSON.parse(data);
        } catch {
          throw new ApiError(
            "The response stream was unreadable. Please try again.",
            502,
          );
        }
        const event = chatEventSchema.safeParse(raw);
        if (!event.success)
          throw new ApiError(
            "The response stream was invalid. Please try again.",
            502,
          );
        if (event.data.type === "progress") onProgress(event.data.step);
        else if (event.data.type === "result") return event.data.result;
        else
          return parseResponse(
            Response.json(event.data.error, {
              status: event.data.error.status,
            }),
            answerSchema,
          );
      }
      if (done)
        throw new ApiError(
          "The connection ended before the answer was ready. Please try again.",
          502,
        );
    }
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
export const api = {
  documents: (signal?: AbortSignal) =>
    request("documents", documentListSchema, { signal }),
  health: (signal?: AbortSignal) => request("health", healthSchema, { signal }),
  job: (id: string) => request(`jobs/${encodeURIComponent(id)}`, jobSchema),
  upload: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request("documents", jobSchema, { method: "POST", body });
  },
  reindex: (id: string) =>
    request(`documents/${encodeURIComponent(id)}/reindex`, jobSchema, {
      method: "POST",
    }),
  remove: (id: string) =>
    request(
      `documents/${encodeURIComponent(id)}`,
      z.object({ status: z.string() }),
      { method: "DELETE" },
    ),
  chat: async (
    message: string,
    conversationId: string | undefined,
    docIds: string[] | null,
    signal: AbortSignal,
    onProgress: (step: ProgressStep) => void,
  ) => {
    const response = await fetch("/api/backend/chat/stream", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      cache: "no-store",
      signal,
      body: JSON.stringify({
        message,
        ...(conversationId ? { conversation_id: conversationId } : {}),
        ...(docIds !== null ? { filters: { doc_ids: docIds } } : {}),
      }),
    });
    return readChatStream(response, onProgress);
  },
};
export function errorText(error: unknown) {
  return error instanceof Error
    ? error.message
    : "Something went wrong. Please try again.";
}
