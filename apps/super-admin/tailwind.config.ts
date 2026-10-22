import preset from "@ai-pos/design-tokens/tailwind-preset";
import type { Config } from "tailwindcss";

export default {
  presets: [preset as Config],
  content: ["./index.html", "./src/**/*.{ts,tsx}", "../../packages/ui/src/**/*.{ts,tsx}"],
  darkMode: "class",
} satisfies Config;
