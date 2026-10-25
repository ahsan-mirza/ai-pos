import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

const envDir = "../../";

export default defineConfig(({ mode }) => {
  const current = loadEnv(mode, envDir, "VITE_");
  const production = mode === "production" ? current : loadEnv("production", envDir, "VITE_");
  // A local .env often has no store host, so the activation screen fell back to axizpos.com.
  // Use the production file's host (the VM IP) unless this mode sets its own.
  const tenantDomain = current.VITE_TENANT_BASE_DOMAIN || production.VITE_TENANT_BASE_DOMAIN;
  return {
    envDir,
    plugins: [react()],
    resolve: { dedupe: ["react", "react-dom", "lucide-react"] },
    clearScreen: false,
    server: {
      port: 1420,
      strictPort: true,
    },
    envPrefix: ["VITE_"],
    define: tenantDomain
      ? { "import.meta.env.VITE_TENANT_BASE_DOMAIN": JSON.stringify(tenantDomain) }
      : undefined,
  };
});
