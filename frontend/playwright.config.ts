import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL: process.env.FRONTEND_TEST_URL || "http://127.0.0.1:3011",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "npm run dev -- --port 3011",
    url: "http://127.0.0.1:3011",
    reuseExistingServer: !process.env.CI,
    env: {
      METRO_API_URL: process.env.METRO_API_URL || "http://127.0.0.1:8011",
    },
  },
});
