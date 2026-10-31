import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";
import { defineConfig } from "vite";
import { pwaManifest } from "./src/pwa/manifest";

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
  resolve: { dedupe: ["react", "react-dom", "lucide-react"] },
  server: {
    port: 5173,
    strictPort: true,
    // Store portals in development: http://demo.localhost:5173 resolves the "demo" tenant.
    allowedHosts: [".localhost"],
  },
});
