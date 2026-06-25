import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  // For GitHub Pages project sites the app is served from /<repo>/, so the asset base
  // must match. Set VITE_BASE="/<repo>/" in CI; defaults to "/" for local dev.
  base: process.env.VITE_BASE || "/",
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: { port: 5173 },
});
