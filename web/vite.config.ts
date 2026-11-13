import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development the API runs separately on port 8000; in production Firebase
// Hosting forwards /api to Cloud Run, so the browser always uses the same origin.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } },
});
