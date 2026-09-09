// defineConfig comes from "vitest/config" so the `test` block below is typed
// correctly — vitest/config re-exports vite's defineConfig with the extra
// `test` field on UserConfig.
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

// The bench site this dev server proxies to. Override per machine; never
// hard-code one farm's URL into the repo.
const FRAPPE_URL = process.env.VITE_FRAPPE_URL || "http://kaitet.local:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  // Frappe serves the built bundle out of the app's public/ folder, so every
  // asset URL the bundle emits has to be absolute under /assets.
  base: "/assets/upande_livestock/dist/",
  build: {
    outDir: "../upande_livestock/public/dist",
    emptyOutDir: true,
    manifest: true,
    cssCodeSplit: false,
    rollupOptions: {
      output: {
        entryFileNames: "livestock-[hash].js",
        assetFileNames: (assetInfo) => {
          const name = assetInfo.name || "";
          if (name.endsWith(".css")) return "livestock-[hash].css";
          return "assets/[name]-[hash][extname]";
        },
        chunkFileNames: "chunks/[name]-[hash].js",
      },
    },
  },
  server: {
    port: 5174,
    proxy: {
      "/api": { target: FRAPPE_URL, changeOrigin: true },
      "/method": { target: FRAPPE_URL, changeOrigin: true },
      "/assets": { target: FRAPPE_URL, changeOrigin: true },
      "/files": { target: FRAPPE_URL, changeOrigin: true },
      "/private": { target: FRAPPE_URL, changeOrigin: true },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
  },
});
