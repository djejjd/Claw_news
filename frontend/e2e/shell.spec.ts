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

test("wraps a long unbroken article title on a narrow viewport", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/");

  await page.getByRole("link", { name: "测试公共文章" }).evaluate((link) => {
    link.textContent = "a".repeat(300);
  });

  await expect(page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).resolves.toBe(true);
});

test("reaches the seeded public router through the Vite API proxy", async ({ request }) => {
  const response = await request.get("/api/public/articles");

  expect(response.ok()).toBeTruthy();
  const payload = await response.json();
  expect(payload.page).toBe(1);
  expect(payload.page_size).toBe(20);
  expect(payload.total).toBe(1);
  expect(payload.items).toEqual([expect.objectContaining({ title: "测试公共文章" })]);
});

test("browses the seeded articles with source filtering", async ({ page }) => {
  await page.goto("/articles");

  await expect(page.getByRole("heading", { level: 1, name: "最近十天" })).toBeVisible();
  await expect(page.getByText("测试公共文章")).toBeVisible();

  await page.getByLabel("按来源筛选").selectOption("test-source");
  await expect(page).toHaveURL(/\/articles\?source=test-source$/);
  await expect(page.getByText("测试公共文章")).toBeVisible();
});

test("moves between server pages and shows the current page in the URL", async ({ page }) => {
  await page.route("**/api/public/articles**", async (route) => {
    const requestUrl = new URL(route.request().url());
    const currentPage = requestUrl.searchParams.get("page") || "1";
    const item = currentPage === "2"
      ? { id: 2, title: "第二页新闻", original_url: "https://example.test/two", category: "ai", topic: null, summary: "第二页摘要", published_at: "2026-08-17T09:00:00+00:00", fetched_at: "2026-08-17T09:01:00+00:00", source: { name: "test-source", display_name: "测试来源", site_url: "https://example.test" } }
      : { id: 1, title: "第一页新闻", original_url: "https://example.test/one", category: "ai", topic: null, summary: "第一页摘要", published_at: "2026-08-17T10:00:00+00:00", fetched_at: "2026-08-17T10:01:00+00:00", source: { name: "test-source", display_name: "测试来源", site_url: "https://example.test" } };
    await route.fulfill({ json: { items: [item], page: Number(currentPage), page_size: 1, total: 2 } });
  });
  await page.goto("/articles");

  await expect(page.getByText("第一页新闻")).toBeVisible();
  await page.getByRole("button", { name: "下一页" }).click();
  await expect(page).toHaveURL(/\/articles\?page=2$/);
  await expect(page.getByText("第二页新闻")).toBeVisible();
});

test("shows an empty state for an unknown source", async ({ page }) => {
  await page.goto("/articles?source=missing-source");

  await expect(page.getByRole("heading", { level: 2, name: "暂无新闻" })).toBeVisible();
  await expect(page.getByText("当前筛选条件下没有可浏览的公开新闻。")).toBeVisible();
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
