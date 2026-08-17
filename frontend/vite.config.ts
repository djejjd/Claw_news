import { defineConfig } from "vitest/config";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  server: { proxy: { "/api": { target: process.env.VITE_API_TARGET ?? "http://127.0.0.1:8001", changeOrigin: true } } },
  test: { environment: "jsdom", exclude: ["e2e/**", "node_modules/**", "dist/**"] },
});
