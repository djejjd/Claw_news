import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PublicApiError } from "../src/api/client";
import { getArticles, getSources, type ArticlePage } from "../src/api/articles";
import ArticlesPage from "../src/pages/ArticlesPage.vue";

vi.mock("../src/api/articles", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/api/articles")>();
  return { ...actual, getArticles: vi.fn(), getSources: vi.fn() };
});

const mockedGetArticles = vi.mocked(getArticles);
const mockedGetSources = vi.mocked(getSources);

const article = (id: number, source = "source-one") => ({
  id,
  title: `文章 ${id}`,
  original_url: `https://example.test/${id}`,
  category: "ai",
  topic: "主题",
  summary: `摘要 ${id}`,
  published_at: "2026-08-17T10:00:00+00:00",
  fetched_at: "2026-08-17T10:01:00+00:00",
  source: { name: source, display_name: source === "source-one" ? "来源一" : "来源二", site_url: null },
});

const page = (items = [article(1)], overrides: Partial<ArticlePage> = {}): ArticlePage => ({
  items,
  page: 1,
  page_size: 20,
  total: items.length,
  ...overrides,
});

describe("ArticlesPage", () => {
  beforeEach(() => {
    window.history.replaceState({}, "", "/articles");
    mockedGetArticles.mockReset();
    mockedGetSources.mockReset();
    mockedGetSources.mockResolvedValue([
      { name: "source-one", display_name: "来源一", site_url: null },
      { name: "source-two", display_name: "来源二", site_url: null },
    ]);
    mockedGetArticles.mockResolvedValue(page());
  });

  it("shows a loading state while the article request is pending", () => {
    mockedGetArticles.mockReturnValue(new Promise(() => {}));
    const wrapper = mount(ArticlesPage);

    expect(wrapper.get('[aria-live="polite"]').text()).toContain("正在加载新闻");
  });

  it("renders public articles, source options and safe external links", async () => {
    const wrapper = mount(ArticlesPage);
    await flushPromises();

    expect(wrapper.get("h1").text()).toContain("最近十天");
    expect(wrapper.text()).toContain("文章 1");
    expect(wrapper.findAll("select option").map((option) => option.text())).toEqual([
      "全部来源",
      "来源一",
      "来源二",
    ]);
    expect(wrapper.get('a[href="https://example.test/1"]').attributes("target")).toBe("_blank");
  });

  it("resets page on each source change and sends the stable source name", async () => {
    mockedGetArticles
      .mockResolvedValueOnce(page([article(1)], { total: 41 }))
      .mockResolvedValueOnce(page([article(2, "source-two")], { total: 1 }));
    const wrapper = mount(ArticlesPage);
    await flushPromises();

    await wrapper.get("select").setValue("source-two");
    await flushPromises();

    expect(mockedGetArticles).toHaveBeenNthCalledWith(1, { source: undefined, page: 1 });
    expect(mockedGetArticles).toHaveBeenNthCalledWith(2, { source: "source-two", page: 1 });
    expect(wrapper.text()).toContain("文章 2");
  });

  it("uses server pagination and shows an empty result without fallback content", async () => {
    mockedGetArticles
      .mockResolvedValueOnce(page([article(1)], { total: 21 }))
      .mockResolvedValueOnce(page([], { page: 2, total: 21 }));
    const wrapper = mount(ArticlesPage);
    await flushPromises();

    await wrapper.get("button:last-of-type").trigger("click");
    await flushPromises();

    expect(mockedGetArticles).toHaveBeenNthCalledWith(2, { source: undefined, page: 2 });
    expect(wrapper.text()).toContain("暂无新闻");
    expect(wrapper.text()).not.toContain("文章 1");
  });

  it("distinguishes service failures and network failures", async () => {
    mockedGetArticles.mockRejectedValueOnce(new PublicApiError(503, "publication_unavailable", "不可用"));
    const wrapper = mount(ArticlesPage);
    await flushPromises();
    expect(wrapper.get('[aria-live="assertive"]').text()).toContain("新闻服务暂不可用");

    mockedGetArticles.mockRejectedValueOnce(new PublicApiError(0, "network_error", "不可用"));
    await wrapper.get('[aria-live="assertive"] button').trigger("click");
    await flushPromises();
    expect(wrapper.get('[aria-live="assertive"]').text()).toContain("网络连接不可用");
  });

  it("clears stale sources when a refresh fails", async () => {
    mockedGetSources.mockResolvedValueOnce([
      { name: "source-one", display_name: "来源一", site_url: null },
    ]).mockRejectedValueOnce(new PublicApiError(503, "publication_unavailable", "不可用"));
    const wrapper = mount(ArticlesPage);
    await flushPromises();
    expect(wrapper.findAll("select option").map((option) => option.text())).toContain("来源一");

    await (wrapper.vm as unknown as { loadSources: () => Promise<void> }).loadSources();
    await flushPromises();

    expect(wrapper.findAll("select option").map((option) => option.text())).toEqual(["全部来源"]);
    expect(wrapper.get('[role="status"]').text()).toContain("来源列表加载失败");
  });
});
