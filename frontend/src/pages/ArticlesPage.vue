<script setup lang="ts">
import { onMounted } from "vue";

import ExternalArticleLink from "../components/ExternalArticleLink.vue";
import { displayCategory } from "./digestState";
import { useArticlesState } from "./articlesState";

const {
  articles,
  sources,
  selectedSource,
  page,
  isLoading,
  error,
  sourcesError,
  totalPages,
  failureMessage,
  sourceFailureMessage,
  loadArticles,
  loadSources,
  selectSource,
  goToPage,
} = useArticlesState();

/** @type {(event: Event) => void} */
// @ts-expect-error Vue supplies the event callback type in the template.
const handleSourceChange = (event) => {
  if (event.target instanceof HTMLSelectElement) void selectSource(event.target.value);
};

onMounted(() => {
  void Promise.all([loadSources(), loadArticles()]);
});
</script>

<template>
  <section class="articles-page">
    <header class="page-heading">
      <div>
        <p class="page-kicker">Claw News / 新闻流</p>
        <h1>最近十天</h1>
        <p class="page-intro">浏览已发布的公开新闻，按来源筛选并跳转原文。</p>
      </div>
      <label class="source-filter">
        <span>来源</span>
        <select
          :value="selectedSource"
          aria-label="按来源筛选"
          @change="handleSourceChange"
        >
          <option value="">全部来源</option>
          <option v-for="source in sources" :key="source.name" :value="source.name">{{ source.display_name }}</option>
        </select>
      </label>
    </header>

    <p v-if="sourcesError" class="inline-error" role="status">
      {{ sourceFailureMessage }}
      <button type="button" class="text-button" @click="loadSources">重试</button>
    </p>

    <section v-if="isLoading" class="page-state" aria-live="polite">正在加载新闻...</section>
    <section v-else-if="error" class="page-state page-state--error" aria-live="assertive">
      <h2>新闻加载失败</h2>
      <p>{{ failureMessage }}</p>
      <button type="button" @click="loadArticles">重试</button>
    </section>
    <section v-else-if="!articles?.items.length" class="page-state" aria-live="polite">
      <h2>暂无新闻</h2>
      <p>当前筛选条件下没有可浏览的公开新闻。</p>
    </section>
    <template v-else>
      <ol class="article-list">
        <li v-for="article in articles.items" :key="article.id" class="article-card">
          <p class="item-meta">
            {{ article.source.display_name }} <span>{{ displayCategory(article.category) }}</span>
            <time :datetime="article.published_at || article.fetched_at">{{ article.published_at || article.fetched_at }}</time>
          </p>
          <h2><ExternalArticleLink :url="article.original_url">{{ article.title }}</ExternalArticleLink></h2>
          <p v-if="article.topic" class="article-topic">{{ article.topic }}</p>
          <p v-if="article.summary" class="article-summary">{{ article.summary }}</p>
        </li>
      </ol>
      <nav v-if="totalPages > 1" class="pagination" aria-label="新闻分页">
        <button type="button" :disabled="page === 1" @click="goToPage(page - 1)">上一页</button>
        <span>第 {{ page }} / {{ totalPages }} 页</span>
        <button type="button" :disabled="page === totalPages" @click="goToPage(page + 1)">下一页</button>
      </nav>
    </template>
  </section>
</template>
