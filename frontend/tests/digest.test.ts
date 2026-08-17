import { describe, expect, it, vi } from "vitest";

import { getCurrentDigest } from "../src/api/digest";

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
