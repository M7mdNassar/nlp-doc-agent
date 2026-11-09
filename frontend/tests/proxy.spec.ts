import { test, expect } from "@playwright/test";
import { proxyRequest } from "../src/lib/proxy";

test("proxy rejects arbitrary backend paths", async () => {
  const response = await proxyRequest(
    new Request("http://localhost:3000/api/backend/admin"),
    ["admin"],
  );
  expect(response.status).toBe(404);
});
test("proxy rejects cross-origin mutations before contacting the backend", async () => {
  const response = await proxyRequest(
    new Request("http://localhost:3000/api/backend/documents", {
      method: "POST",
      headers: { origin: "http://another-site.test" },
    }),
    ["documents"],
  );
  expect(response.status).toBe(403);
});
test("proxy rejects oversized upload declarations before buffering", async () => {
  const response = await proxyRequest(
    new Request("http://localhost:3000/api/backend/documents", {
      method: "POST",
      headers: { "content-length": String(60 * 1024 * 1024) },
    }),
    ["documents"],
  );
  expect(response.status).toBe(413);
});

test("proxy handles malformed and opaque origins without throwing", async () => {
  for (const origin of ["null", "invalid", "https://localhost:3000"]) {
    const response = await proxyRequest(
      new Request("http://localhost:3000/api/backend/documents", {
        method: "POST",
        headers: { origin },
      }),
      ["documents"],
    );
    expect(response.status).toBe(403);
  }
});

test("container bind addresses preserve browser origins without forwarding credentials", async () => {
  const originalFetch = globalThis.fetch;
  const forwarded: Headers[] = [];
  globalThis.fetch = async (_url, init) => {
    forwarded.push(new Headers(init?.headers));
    return Response.json({ status: "ok" });
  };
  try {
    for (const host of ["localhost:3000", "127.0.0.1:3000"]) {
      const response = await proxyRequest(
        new Request("http://0.0.0.0:3000/api/backend/documents", {
          method: "POST",
          headers: {
            host,
            origin: `http://${host}`,
            cookie: "private=secret",
            authorization: "Bearer secret",
            "content-type": "application/json",
          },
          body: "{}",
        }),
        ["documents"],
      );
      expect(response.status).toBe(200);
    }
    const rejected = await proxyRequest(
      new Request("http://0.0.0.0:3000/api/backend/documents", {
        method: "POST",
        headers: {
          host: "localhost:3000",
          origin: "http://untrusted.test",
          "x-forwarded-host": "untrusted.test",
        },
      }),
      ["documents"],
    );
    expect(rejected.status).toBe(403);
    expect(forwarded).toHaveLength(2);
    for (const headers of forwarded) {
      expect(headers.has("cookie")).toBe(false);
      expect(headers.has("authorization")).toBe(false);
      expect(headers.get("content-type")).toBe("application/json");
    }
  } finally {
    globalThis.fetch = originalFetch;
  }
});
