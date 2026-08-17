import { defineConfig } from "@playwright/test";

const testPython = process.env.CLAW_NEWS_E2E_PYTHON ?? "../venv/bin/python";

export default defineConfig({
  testDir: "./e2e",
  use: { baseURL: "http://127.0.0.1:4173" },
  webServer: [
    {
      command: `${testPython} ../tests/frontend_e2e_api_server.py --port 8001`,
      port: 8001,
      reuseExistingServer: false,
    },
    {
      command: "npm run dev -- --host 127.0.0.1 --port 4173",
      env: { VITE_API_TARGET: "http://127.0.0.1:8001" },
      port: 4173,
      reuseExistingServer: false,
    },
  ],
});
