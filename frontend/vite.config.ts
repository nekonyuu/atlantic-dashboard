/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    // en dev, l'API tourne à part (uvicorn sur 8000)
    proxy: { "/api": process.env.API_URL ?? "http://127.0.0.1:8000" },
  },
  build: { outDir: "dist", sourcemap: false },
  test: { environment: "jsdom", setupFiles: ["./src/test/setup.ts"], globals: false },
});
