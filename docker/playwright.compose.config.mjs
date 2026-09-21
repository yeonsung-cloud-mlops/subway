import { defineConfig } from "../frontend/node_modules/@playwright/test/index.mjs";

export default defineConfig({
  testDir: "../frontend/tests",
  outputDir: "../var/compose-browser-tests",
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL: process.env.FRONTEND_TEST_URL || "http://127.0.0.1:8080",
    trace: "retain-on-failure",
  },
});
