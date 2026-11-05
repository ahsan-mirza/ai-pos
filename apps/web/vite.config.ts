import path from "node:path";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";
import { defineConfig } from "vite";
import { pwaManifest } from "./src/pwa/manifest";

const root = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  envDir: "../../",
  plugins: [
    react(),
    VitePWA({
      strategies: "injectManifest",
      srcDir: "service-worker",
      filename: "sw.ts",
      injectRegister: false,
      manifest: pwaManifest,
      manifestFilename: "manifest.webmanifest",
      injectManifest: {
        // Classic script so registration can use /sw.js without type: "module".
        rollupFormat: "iife",
        globPatterns: ["**/*.{js,css,html,svg,png,ico,woff2,webmanifest}"],
        // The portal shell is one bundle, currently about 2.4 MB.
        maximumFileSizeToCacheInBytes: 4 * 1024 * 1024,
      },
      devOptions: { enabled: false },
    }),
  ],
  resolve: {
    alias: [
      { find: "@reach", replacement: path.resolve(root, "../../plugins/reach/frontend") },
      { find: "@ai-pos/shared-types", replacement: path.resolve(root, "../../packages/shared-types/src/index.ts") },
      { find: "@ai-pos/ui", replacement: path.resolve(root, "../../packages/ui/src/index.ts") },
      { find: "react/jsx-runtime", replacement: path.resolve(root, "node_modules/react/jsx-runtime.js") },
      { find: "react", replacement: path.resolve(root, "node_modules/react") },
      { find: "react-dom", replacement: path.resolve(root, "node_modules/react-dom") },
      { find: "react-router-dom", replacement: path.resolve(root, "node_modules/react-router-dom") },
    ],
    dedupe: ["react", "react-dom", "lucide-react"],
  },
  server: {
    port: 5173,
    strictPort: true,
    // Store portals in development: http://demo.localhost:5173 resolves the "demo" tenant.
    allowedHosts: [".localhost"],
  },
});
