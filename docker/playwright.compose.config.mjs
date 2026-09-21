import { defineConfig } from "../frontend/node_modules/@playwright/test/index.mjs";

const baseURL = process.env.FRONTEND_TEST_URL || "http://127.0.0.1:8080";
process.env.ENRICHMENT_API_URL ||= baseURL;

export default defineConfig({
  testDir: "../frontend/tests",
  outputDir: "../var/compose-browser-tests",
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL,
    trace: "retain-on-failure",
  },
});
