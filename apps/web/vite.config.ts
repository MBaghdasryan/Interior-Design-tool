import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// API is proxied in development so the browser never needs CORS or secrets.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: process.env.VITE_API_PROXY || "http://localhost:8000", changeOrigin: true } },
  },
  build: { chunkSizeWarningLimit: 1500 },
});
