import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig(({ mode }) => ({
  base: mode === "production" ? "/admin74246/" : "/",
  envDir: "../../",
  plugins: [react()],
  resolve: { dedupe: ["react", "react-dom", "lucide-react"] },
  server: { port: 5174, strictPort: true },
  test: {
    environment: "happy-dom",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
}));
