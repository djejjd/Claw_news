import { expect, test } from "@playwright/test";

test("renders the public shell and navigation", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("link", { name: "日报" })).toBeVisible();
  await page.getByRole("link", { name: "新闻" }).click();
  await expect(page).toHaveURL(/\/articles$/);
});

test("renders the seeded public digest through the Vite API proxy", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { level: 1, name: "2026-08-17" })).toBeVisible();
  await expect(page.getByText("测试核心摘要")).toBeVisible();
  const articleLink = page.getByRole("link", { name: "测试公共文章" });
  await expect(articleLink).toHaveAttribute("href", "https://example.test/article");
  await expect(articleLink).toHaveAttribute("target", "_blank");
  await expect(articleLink).toHaveAttribute("rel", "noopener noreferrer");
});

test("keeps the public digest readable on a narrow viewport", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/");

  await expect(page.getByRole("heading", { level: 1, name: "2026-08-17" })).toBeVisible();
  await expect(page.getByRole("link", { name: "测试公共文章" })).toBeVisible();
  await expect(page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).resolves.toBe(true);
});

test("reaches the seeded public router through the Vite API proxy", async ({ request }) => {
  const response = await request.get("/api/public/articles");

  expect(response.ok()).toBeTruthy();
  expect(await response.json()).toEqual({
    items: [expect.objectContaining({ title: "测试公共文章" })],
    page: 1,
    page_size: 20,
    total: 1,
  });
});

test("reports a browser network disconnect as a displayable public API error", async ({ page }) => {
  await page.route("**/api/public/articles", (route) => route.abort("connectionfailed"));
  await page.goto("/");

  const result = await page.evaluate(async () => {
    const { fetchPublicJson, PublicApiError } = await import("/src/api/client.ts");
    try {
      await fetchPublicJson("/api/public/articles");
      return null;
    } catch (error) {
      return error instanceof PublicApiError ? { code: error.code, status: error.status } : null;
    }
  });

  expect(result).toEqual({ code: "network_error", status: 0 });
});
