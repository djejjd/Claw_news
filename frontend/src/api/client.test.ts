import { describe, expect, it, vi } from "vitest";

import { PublicApiError, fetchPublicJson } from "./client";

describe("fetchPublicJson", () => {
  it("uses the same-origin public API path and returns decoded JSON", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(fetchPublicJson<{ items: [] }>("/api/public/articles", fetcher)).resolves.toEqual({
      items: [],
    });
    expect(fetcher).toHaveBeenCalledWith("/api/public/articles", { credentials: "omit" });
  });

  it("converts a public API error response into an explicit displayable error", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: { code: "publication_unavailable", message: "暂不可用" } }), {
        status: 503,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(fetchPublicJson("/api/public/digests", fetcher)).rejects.toEqual(
      new PublicApiError(503, "publication_unavailable", "暂不可用"),
    );
  });

  it("converts network failures into an explicit displayable error", async () => {
    const fetcher = vi.fn().mockRejectedValue(new TypeError("network unavailable"));

    await expect(fetchPublicJson("/api/public/articles", fetcher)).rejects.toEqual(
      new PublicApiError(0, "network_error", "公共内容服务暂不可用"),
    );
  });

  it("rejects paths outside the public API boundary before sending a request", async () => {
    const fetcher = vi.fn();

    await expect(fetchPublicJson("/api/private/articles", fetcher)).rejects.toEqual(
      new PublicApiError(0, "invalid_public_path", "公共内容服务暂不可用"),
    );
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("rejects a public-looking path that normalizes outside the public API boundary", async () => {
    const fetcher = vi.fn();

    await expect(fetchPublicJson("/api/public/../private/articles", fetcher)).rejects.toEqual(
      new PublicApiError(0, "invalid_public_path", "公共内容服务暂不可用"),
    );
    expect(fetcher).not.toHaveBeenCalled();
  });
});
