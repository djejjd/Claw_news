import { createApp } from "vue";
import { createRouter, createWebHistory } from "vue-router";

import App from "./App.vue";
import DigestPage from "./pages/DigestPage.vue";
import ArticlesPage from "./pages/ArticlesPage.vue";
import "./styles/main.css";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", component: DigestPage },
    { path: "/articles", component: ArticlesPage },
  ],
});

createApp(App).use(router).mount("#app");
