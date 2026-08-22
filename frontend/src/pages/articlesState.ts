import { computed, ref } from "vue";

import { PublicApiError } from "../api/client";
import { getArticles, getSources, type ArticlePage, type PublicSource } from "../api/articles";

export function useArticlesState() {
  const query = typeof window === "undefined" ? new URLSearchParams() : new URLSearchParams(window.location.search);
  const initialPage = Number(query.get("page"));
  const articles = ref<ArticlePage | null>(null);
  const sources = ref<PublicSource[]>([]);
  const selectedSource = ref(query.get("source") || "");
  const page = ref(Number.isInteger(initialPage) && initialPage > 0 ? initialPage : 1);
  const isLoading = ref(true);
  const error = ref<PublicApiError | null>(null);
  const sourcesError = ref<PublicApiError | null>(null);
  let requestSequence = 0;

  const totalPages = computed(() => {
    if (!articles.value || articles.value.total === 0) return 1;
    return Math.ceil(articles.value.total / articles.value.page_size);
  });

  const failureMessage = computed(() => {
    if (error.value?.code === "network_error") return "网络连接不可用，请检查网络后重试。";
    if (error.value?.status === 503) return "新闻服务暂不可用，请稍后重试。";
    return "新闻加载失败，请稍后重试。";
  });

  const sourceFailureMessage = computed(() =>
    sourcesError.value?.code === "network_error" ? "来源列表暂时不可用。" : "来源列表加载失败。",
  );

  function syncQuery() {
    if (typeof window === "undefined") return;
    const next = new URLSearchParams();
    if (selectedSource.value) next.set("source", selectedSource.value);
    if (page.value > 1) next.set("page", String(page.value));
    const suffix = next.toString();
    window.history.replaceState({}, "", `${window.location.pathname}${suffix ? `?${suffix}` : ""}`);
  }

  async function loadSources() {
    sourcesError.value = null;
    // 重新请求期间不保留旧来源，避免失败时把过期筛选项当作当前结果。
    sources.value = [];
    try {
      sources.value = await getSources();
    } catch (caught) {
      sourcesError.value = caught instanceof PublicApiError ? caught : new PublicApiError(0, "network_error", "公共内容服务暂不可用");
    }
  }

  async function loadArticles() {
    const sequence = ++requestSequence;
    isLoading.value = true;
    error.value = null;
    articles.value = null;
    try {
      const result = await getArticles({ source: selectedSource.value || undefined, page: page.value });
      if (sequence !== requestSequence) return;
      articles.value = result;
    } catch (caught) {
      if (sequence !== requestSequence) return;
      error.value = caught instanceof PublicApiError ? caught : new PublicApiError(0, "network_error", "公共内容服务暂不可用");
    } finally {
      if (sequence === requestSequence) isLoading.value = false;
    }
  }

  async function selectSource(source: string) {
    selectedSource.value = source;
    page.value = 1;
    syncQuery();
    await loadArticles();
  }

  async function goToPage(nextPage: number) {
    if (nextPage < 1 || nextPage > totalPages.value || nextPage === page.value) return;
    page.value = nextPage;
    syncQuery();
    await loadArticles();
  }

  return { articles, sources, selectedSource, page, isLoading, error, sourcesError, totalPages, failureMessage, sourceFailureMessage, loadArticles, loadSources, selectSource, goToPage };
}
