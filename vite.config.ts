/// <reference types="vitest/config" />
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// SITE_UNLISTED=true -> ask search engines not to index the site (it stays reachable by link).
// This is NOT access control: anyone with the URL can open it.
function unlisted(): Plugin {
  const on = process.env.SITE_UNLISTED === "true";
  return {
    name: "unlisted",
    transformIndexHtml: (html) =>
      on ? html.replace("</head>", '    <meta name="robots" content="noindex, nofollow" />\n  </head>') : html,
    generateBundle() {
      this.emitFile({ type: "asset", fileName: "robots.txt",
        source: on ? "User-agent: *\nDisallow: /\n" : "User-agent: *\nAllow: /\n" });
    },
  };
}

// base "./" keeps every asset path relative, so the build works at any URL prefix
// (GitHub Pages project sites, Netlify, a local file server) without configuration.
export default defineConfig({
  base: "./",
  plugins: [react(), tailwindcss(), unlisted()],
  build: {
    target: "es2022",
    rollupOptions: {
      output: {
        manualChunks: (id: string) =>
          /node_modules\/(recharts|d3-|victory-vendor)/.test(id) ? "charts"
            : id.includes("node_modules/@tanstack") ? "table" : undefined,
      },
    },
  },
  test: { environment: "jsdom", include: ["src/**/*.test.ts", "src/**/*.test.tsx"] },
});
