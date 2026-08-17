import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PublicApiError } from "../src/api/client";
import type { DigestPublic } from "../src/api/digest";
import { getCurrentDigest } from "../src/api/digest";
import DigestPage from "../src/pages/DigestPage.vue";

vi.mock("../src/api/digest", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/api/digest")>();
  return { ...actual, getCurrentDigest: vi.fn() };
});

const mockedGetCurrentDigest = vi.mocked(getCurrentDigest);

const digest: DigestPublic = {
  date: "2026-08-17",
  version: 1,
  published_at: "2026-08-17T11:00:00+00:00",
  daily_judgement: "今日值得关注的更新较多。",
  items: [
    {
      position: 2,
      core_summary: "第二条核心摘要",
      importance: "high",
      trend: "up",
      topic_label: null,
      article: {
        id: 2,
        title: "第二篇文章",
        original_url: "https://example.test/two",
        category: "ai",
        topic: null,
        summary: "",
        published_at: null,
        fetched_at: "2026-08-17T10:00:00+00:00",
        source: { name: "two", display_name: "来源二", site_url: null },
      },
    },
    {
      position: 1,
      core_summary: "第一条核心摘要",
      importance: "medium",
      trend: "steady",
      topic_label: "模型",
      article: {
        id: 1,
        title: "第一篇文章",
        original_url: "https://example.test/one",
        category: "tool",
        topic: "模型",
        summary: "第一篇公开摘要",
        published_at: "2026-08-17T09:00:00+00:00",
        fetched_at: "2026-08-17T09:01:00+00:00",
        source: { name: "one", display_name: "来源一", site_url: "https://source.example.test" },
      },
    },
  ],
  github_projects: [
    { position: 2, full_name: "example/two", recommendation: "第二个推荐" },
    { position: 1, full_name: "example/one", recommendation: "第一个推荐" },
  ],
};

describe("DigestPage", () => {
  beforeEach(() => {
    mockedGetCurrentDigest.mockReset();
  });

  it("shows a readable loading status before the digest resolves", () => {
    mockedGetCurrentDigest.mockReturnValue(new Promise(() => {}));

    const wrapper = mount(DigestPage);

    expect(wrapper.get('[aria-live="polite"]').text()).toContain("正在加载日报");
  });

  it("renders API items and projects in position order without inventing an empty summary", async () => {
    mockedGetCurrentDigest.mockResolvedValue(digest);

    const wrapper = mount(DigestPage);
    await flushPromises();

    expect(wrapper.get("h1").text()).toContain("2026-08-17");
    expect(wrapper.text()).toContain(digest.daily_judgement);
    expect(wrapper.findAll("article h2").map((heading) => heading.text())).toEqual([
      "第一篇文章",
      "第二篇文章",
    ]);
    expect(wrapper.text()).not.toContain("第二篇公开摘要");
    expect(wrapper.findAll('[data-testid="github-project"]').map((item) => item.text())).toEqual([
      expect.stringContaining("example/one"),
      expect.stringContaining("example/two"),
    ]);

    const articleLink = wrapper.get('a[href="https://example.test/one"]');
    expect(articleLink.attributes("target")).toBe("_blank");
    expect(articleLink.attributes("rel")).toBe("noopener noreferrer");
  });

  it("distinguishes an absent digest from service and network failures, and retries", async () => {
    mockedGetCurrentDigest.mockRejectedValueOnce(
      new PublicApiError(404, "digest_not_found", "指定日期不存在已发布日报"),
    );
    const wrapper = mount(DigestPage);
    await flushPromises();
    expect(wrapper.get('[aria-live="polite"]').text()).toContain("暂无日报");

    mockedGetCurrentDigest.mockRejectedValueOnce(
      new PublicApiError(503, "publication_unavailable", "公共内容服务暂不可用"),
    );
    await wrapper.get("button").trigger("click");
    await flushPromises();
    expect(wrapper.get('[aria-live="assertive"]').text()).toContain("日报服务暂不可用");

    mockedGetCurrentDigest.mockRejectedValueOnce(
      new PublicApiError(0, "network_error", "公共内容服务暂不可用"),
    );
    await wrapper.get("button").trigger("click");
    await flushPromises();
    expect(wrapper.get('[aria-live="assertive"]').text()).toContain("网络连接不可用");
    expect(mockedGetCurrentDigest).toHaveBeenCalledTimes(3);
  });

  it("shows an unsafe article URL as text instead of a link", async () => {
    mockedGetCurrentDigest.mockResolvedValue({
      ...digest,
      items: [
        {
          ...digest.items[0],
          article: { ...digest.items[0].article, original_url: "javascript:alert(1)" },
        },
      ],
    });

    const wrapper = mount(DigestPage);
    await flushPromises();

    expect(wrapper.text()).toContain("第二篇文章");
    expect(wrapper.find("article a").exists()).toBe(false);
  });
});
