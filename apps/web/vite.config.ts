import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  envDir: "../../",
  plugins: [react()],
  resolve: { dedupe: ["react", "react-dom", "lucide-react"] },
  server: {
    port: 5173,
    strictPort: true,
    // Store portals in development: http://demo.localhost:5173 resolves the "demo" tenant.
    allowedHosts: [".localhost"],
  },
});
