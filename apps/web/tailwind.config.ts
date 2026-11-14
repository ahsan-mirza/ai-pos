import preset from "@ai-pos/design-tokens/tailwind-preset";
import type { Config } from "tailwindcss";

export default {
  presets: [preset as Config],
  content: ["./index.html", "./src/**/*.{ts,tsx}", "../../packages/ui/src/**/*.{ts,tsx}"],
  // `dark` is toggled on <html> by the portal theme switch. The register sets data-theme on its own shell.
  darkMode: "class",
} satisfies Config;
