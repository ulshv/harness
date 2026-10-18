import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// compose sets it to the harness service; `npm run dev` on the host talks to `make up`'s published port
const HARNESS_URL = process.env.HARNESS_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 8080,
    // a busy port fails the start instead of silently moving to 8081
    strictPort: true,
    // same origin for the browser, so harness needs no CORS: /api/chat/stream → harness/chat/stream
    proxy: {
      "/api/": {
        target: HARNESS_URL,
        rewrite: (path) => path.replace(/^\/api(?=\/)/, ""),
        // the proxy pipes the response and only reports upstream errors before the first byte: if harness dies
        // mid-stream, the browser's response would never end. Cut it, so the client sees the stream break.
        configure: (proxy) =>
          proxy.on("proxyRes", (proxyRes, _req, res) =>
            proxyRes.on("close", () => {
              if (!proxyRes.complete) res.destroy();
            }),
          ),
      },
    },
  },
});
