import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    // In development the interface runs on its own port and forwards API calls to the backend.
    proxy: { "/api": "http://127.0.0.1:8080" },
  },
});
