/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  base: "./", // every URL is relative to <base href>, which the server sets to the mount path
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:8765" } }, // backend/tests/dev_server.py
  test: { environment: "jsdom", setupFiles: ["src/test-setup.ts"], include: ["src/**/*.test.{ts,tsx}"] },
});
