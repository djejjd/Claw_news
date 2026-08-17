<script setup lang="ts">
import { onMounted } from "vue";

import ExternalArticleLink from "../components/ExternalArticleLink.vue";
import {
  displayCategory,
  displayImportance,
  displayTrend,
  useDigestState,
} from "./digestState";

const { digest, error, failureMessage, isLoading, loadDigest, sortedItems, sortedProjects } =
  useDigestState();

onMounted(loadDigest);
</script>

<template>
  <section
    v-if="isLoading"
    class="page-state"
    aria-live="polite"
  >
    正在加载日报...
  </section>

  <section
    v-else-if="error?.code === 'digest_not_found'"
    class="page-state"
    aria-live="polite"
  >
    <h1>暂无日报</h1>
    <p>当天尚未发布可浏览的日报。</p>
    <button
      type="button"
      @click="loadDigest"
    >
      重试
    </button>
  </section>

  <section
    v-else-if="error"
    class="page-state page-state--error"
    aria-live="assertive"
  >
    <h1>日报加载失败</h1>
    <p>{{ failureMessage }}</p>
    <button
      type="button"
      @click="loadDigest"
    >
      重试
    </button>
  </section>

  <section
    v-else-if="digest"
    class="digest-page"
  >
    <header class="digest-heading">
      <div>
        <p class="page-kicker">
          Claw News / 公共日报
        </p>
        <h1>{{ digest.date }}</h1>
      </div>
      <div class="daily-journal">
        <p>今日判断</p>
        <p class="daily-judgement">
          {{ digest.daily_judgement }}
        </p>
      </div>
    </header>

    <ol class="digest-list">
      <li
        v-for="item in sortedItems"
        :key="item.article.id"
      >
        <article class="digest-item">
          <p class="item-position">
            {{ String(item.position).padStart(2, "0") }}
          </p>
          <div>
            <p class="item-meta">
              {{ item.article.source.display_name }}
              <span>
                {{ displayCategory(item.article.category) }}
              </span>
            </p>
            <h2>
              <ExternalArticleLink :url="item.article.original_url">
                {{ item.article.title }}
              </ExternalArticleLink>
            </h2>
            <p class="core-summary">
              {{ item.core_summary }}
            </p>
            <p
              v-if="item.article.summary"
              class="article-summary"
            >
              {{ item.article.summary }}
            </p>
            <dl class="item-details">
              <div><dt>重要性</dt><dd>{{ displayImportance(item.importance) }}</dd></div>
              <div><dt>趋势</dt><dd>{{ displayTrend(item.trend) }}</dd></div>
              <div v-if="item.topic_label">
                <dt>主题</dt><dd>{{ item.topic_label }}</dd>
              </div>
            </dl>
          </div>
        </article>
      </li>
    </ol>

    <section
      v-if="sortedProjects.length"
      class="github-projects"
      aria-labelledby="github-heading"
    >
      <h2 id="github-heading">
        GitHub 推荐
      </h2>
      <ol>
        <li
          v-for="project in sortedProjects"
          :key="project.full_name"
          data-testid="github-project"
        >
          <strong>{{ project.full_name }}</strong>
          <p>{{ project.recommendation }}</p>
        </li>
      </ol>
    </section>
  </section>
</template>
