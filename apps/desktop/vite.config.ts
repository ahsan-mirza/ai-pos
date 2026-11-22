import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

const acceptanceDir = fileURLToPath(new URL("./config/acceptance", import.meta.url));
const inventoryAcceptanceDir = fileURLToPath(new URL("./config/inventory-acceptance", import.meta.url));
const offlineAcceptanceDir = fileURLToPath(new URL("./config/offline-acceptance", import.meta.url));
const restaurantAcceptanceDir = fileURLToPath(new URL("./config/restaurant-acceptance", import.meta.url));
const zoomApis: Record<string, string> = {
  "zoom-grocery": "http://127.0.0.1:18090",
  "zoom-electronics": "http://127.0.0.1:18091",
  "zoom-fashion": "http://127.0.0.1:18092",
  "zoom-restaurant": "http://127.0.0.1:18093",
};

export default defineConfig(({ mode }) => {
  const inventoryAcceptance = mode === "inventory-acceptance";
  const offlineAcceptance = mode === "offline-acceptance";
  const restaurantAcceptance = mode === "restaurant-acceptance";
  const zoomAcceptance = mode.startsWith("zoom-");
  const acceptance = mode === "acceptance" || inventoryAcceptance || offlineAcceptance || restaurantAcceptance || zoomAcceptance;
  const envDir = zoomAcceptance
    ? fileURLToPath(new URL(`./config/${mode}`, import.meta.url))
    : restaurantAcceptance
      ? restaurantAcceptanceDir
      : offlineAcceptance
        ? offlineAcceptanceDir
        : inventoryAcceptance
          ? inventoryAcceptanceDir
          : acceptance
            ? acceptanceDir
            : "../../";
  const acceptanceApi = zoomApis[mode]
    ?? (restaurantAcceptance
      ? "http://127.0.0.1:18089"
      : offlineAcceptance
        ? "http://127.0.0.1:18084"
        : inventoryAcceptance
          ? "http://127.0.0.1:18081"
          : "http://127.0.0.1:18080");
  const current = loadEnv(mode, envDir, "VITE_");
  const production = acceptance || mode === "production" ? current : loadEnv("production", envDir, "VITE_");
  // A local .env often has no store host, so the activation screen fell back to axizpos.com.
  // Use the production file's host (the VM IP) unless this mode sets its own.
  // The acceptance mode reads only apps/desktop/config/acceptance and does not use that fallback.
  const tenantDomain = acceptance
    ? current.VITE_TENANT_BASE_DOMAIN
    : current.VITE_TENANT_BASE_DOMAIN || production.VITE_TENANT_BASE_DOMAIN;
  if (acceptance) {
    if (current.VITE_API_BASE_URL !== acceptanceApi) {
      throw new Error(`Acceptance frontend must use ${acceptanceApi} and no other API.`);
    }
    if (!tenantDomain || tenantDomain.includes("axizpos.com") || tenantDomain.includes("130.210.53.214")) {
      throw new Error("Acceptance frontend must not use a production or developer tenant host.");
    }
  }
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
