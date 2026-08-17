import { describe, expect, it } from "vitest";

import { toSafeExternalUrl } from "../src/api/externalUrl";

describe("toSafeExternalUrl", () => {
  it.each([
    ["https://example.test/article", "https://example.test/article"],
    ["http://example.test/article", "http://example.test/article"],
  ])("accepts public %s URLs", (input, expected) => {
    expect(toSafeExternalUrl(input)).toBe(expected);
  });

  it.each(["javascript:alert(1)", "//example.test/article", "http://"]) (
    "rejects a non-public or malformed URL: %s",
    (input) => {
      expect(toSafeExternalUrl(input)).toBeNull();
    },
  );
});
