import { createApp } from "vue";
import { createRouter, createWebHistory } from "vue-router";

import App from "./App.vue";
import "./styles/main.css";

const PlaceholderPage = { template: "<p>公共内容加载中</p>" };

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", component: PlaceholderPage },
    { path: "/articles", component: PlaceholderPage },
  ],
});

createApp(App).use(router).mount("#app");
