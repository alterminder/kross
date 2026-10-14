import { defineConfig, devices } from "@playwright/test";

const port = Number(process.env.PW_PORT ?? 8765); // override when 8765 is taken (another worktree's dev server)

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  workers: 1, // one worker: parallel workers sign in as the same fresh dev user and race its creation (409)
  use: { baseURL: `http://127.0.0.1:${port}/`, trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `cd ../backend && uv run python -m tests.dev_server --fresh --database nlab_e2e --port ${port}`,
    url: `http://127.0.0.1:${port}/api/health`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
