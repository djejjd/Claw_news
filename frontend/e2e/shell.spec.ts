import { expect, test } from "@playwright/test";

test("renders the public shell and navigation", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("link", { name: "日报" })).toBeVisible();
  await page.getByRole("link", { name: "新闻" }).click();
  await expect(page).toHaveURL(/\/articles$/);
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
