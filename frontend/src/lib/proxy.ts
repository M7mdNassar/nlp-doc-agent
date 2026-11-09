const MAX_BODY_BYTES = 51 * 1024 * 1024; // 50 MiB file plus multipart overhead.
const id = "[a-zA-Z0-9_-]+";
const routes: Record<string, RegExp> = {
  GET: new RegExp(`^(health|documents|jobs/${id})$`),
  POST: new RegExp(`^(chat|documents|documents/${id}/reindex)$`),
  DELETE: new RegExp(`^documents/${id}$`),
};

function error(message: string, status: number, code: string) {
  return Response.json(
    { message, code },
    { status, headers: { "Cache-Control": "no-store" } },
  );
}

export async function proxyRequest(request: Request, segments: string[]) {
  const path = segments.join("/");
  if (!routes[request.method]?.test(path))
    return error("This endpoint is not available.", 404, "NOT_FOUND");
  const origin = request.headers.get("origin");
  if (request.method !== "GET" && origin) {
    // Invalid/opaque origins also fail closed, before forwarding any body.
    let sameOrigin = false;
    try {
      const requestUrl = new URL(request.url);
      // Next's standalone server may use its internal bind address in request.url.
      // Host is the browser-facing authority; do not trust X-Forwarded-Host here.
      const host = request.headers.get("host") || requestUrl.host;
      const expectedOrigin = new URL(`${requestUrl.protocol}//${host}`).origin;
      sameOrigin = new URL(origin).origin === expectedOrigin;
    } catch {
      sameOrigin = false;
    }
    if (!sameOrigin)
      return error(
        "Requests must come from this workspace.",
        403,
        "ORIGIN_MISMATCH",
      );
  }
  if (Number(request.headers.get("content-length") || 0) > MAX_BODY_BYTES) {
    return error("Choose a file smaller than 50 MB.", 413, "UPLOAD_TOO_LARGE");
  }
  try {
    let body: ArrayBuffer | undefined;
    if (request.body && request.method !== "GET") {
      const reader = request.body.getReader();
      const chunks: Uint8Array[] = [];
      let size = 0;
      while (true) {
        const next = await reader.read();
        if (next.done) break;
        size += next.value.byteLength;
        if (size > MAX_BODY_BYTES) {
          await reader.cancel();
          return error(
            "Choose a file smaller than 50 MB.",
            413,
            "UPLOAD_TOO_LARGE",
          );
        }
        chunks.push(next.value);
      }
      const bytes = new Uint8Array(size);
      let offset = 0;
      for (const chunk of chunks) {
        bytes.set(chunk, offset);
        offset += chunk.byteLength;
      }
      body = bytes.buffer;
    }
    const backend = (
      process.env.BACKEND_URL || "http://127.0.0.1:8000"
    ).replace(/\/$/, "");
    const headers = new Headers({ Accept: "application/json" });
    const contentType = request.headers.get("content-type");
    if (contentType) headers.set("Content-Type", contentType);
    const timeout =
      path === "chat" ? 600_000 : request.method === "GET" ? 15_000 : 120_000;
    const upstream = await fetch(`${backend}/${path}`, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(timeout)]),
      redirect: "error",
    });
    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        "Content-Type":
          upstream.headers.get("content-type") || "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch (cause) {
    if (cause instanceof Error && cause.name === "TimeoutError")
      return error(
        "The request took too long. Try again in a moment.",
        504,
        "BACKEND_TIMEOUT",
      );
    if (request.signal.aborted)
      return error("The request was cancelled.", 499, "CANCELLED");
    return error(
      "We couldn’t reach the backend. Check that the services are running, then try again.",
      502,
      "BACKEND_UNAVAILABLE",
    );
  }
}
