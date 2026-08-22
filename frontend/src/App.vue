<script setup lang="ts">
import { RouterLink, RouterView } from "vue-router";
</script>

<template>
  <header class="site-header">
    <RouterLink
      class="brand"
      to="/"
    >
      Claw News
    </RouterLink>
    <nav aria-label="主导航">
      <RouterLink to="/">
        日报
      </RouterLink>
      <RouterLink to="/articles">
        新闻
      </RouterLink>
    </nav>
  </header>
  <main>
    <RouterView />
  </main>
</template>
