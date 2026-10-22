import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  envDir: "../../",
  plugins: [react()],
  resolve: { dedupe: ["react", "react-dom", "lucide-react"] },
  server: { port: 5174, strictPort: true },
});
