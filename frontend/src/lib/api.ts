import { z } from "zod";
import {
  answerSchema,
  documentListSchema,
  healthSchema,
  jobSchema,
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
  chat: (
    message: string,
    conversationId: string | undefined,
    docIds: string[] | null,
    signal: AbortSignal,
  ) =>
    request("chat", answerSchema, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal,
      body: JSON.stringify({
        message,
        ...(conversationId ? { conversation_id: conversationId } : {}),
        ...(docIds !== null ? { filters: { doc_ids: docIds } } : {}),
      }),
    }),
};
export function errorText(error: unknown) {
  return error instanceof Error
    ? error.message
    : "Something went wrong. Please try again.";
}
