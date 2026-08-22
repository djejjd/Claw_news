import { describe, expect, it, vi } from "vitest";

import { getCurrentDigest } from "../src/api/digest";
import { getArticles, getSources } from "../src/api/articles";

describe("getCurrentDigest", () => {
  it("requests the default digest without a date query parameter", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ date: "2026-08-17", items: [], github_projects: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(getCurrentDigest(fetcher)).resolves.toMatchObject({ date: "2026-08-17" });
    expect(fetcher).toHaveBeenCalledWith("/api/public/digests", { credentials: "omit" });
  });
});

describe("public article API", () => {
  it("encodes source and page while preserving the server page size contract", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [], page: 2, page_size: 20, total: 0 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await getArticles({ source: "source with spaces", page: 2 }, fetcher);

    expect(fetcher).toHaveBeenCalledWith(
      "/api/public/articles?source=source+with+spaces&page=2",
      { credentials: "omit" },
    );
  });

  it("loads the public source list without leaking query parameters", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } }),
    );

    await getSources(fetcher);

    expect(fetcher).toHaveBeenCalledWith("/api/public/sources", { credentials: "omit" });
  });
});
