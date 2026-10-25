import preset from "@ai-pos/design-tokens/tailwind-preset";
import type { Config } from "tailwindcss";

export default {
  presets: [preset as Config],
  content: ["./index.html", "./src/**/*.{ts,tsx}", "../../packages/ui/src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        canvas: "var(--color-canvas)",
        line: "var(--color-border)",
        charcoal: "var(--color-charcoal)",
        card: "var(--color-card)",
        surface: "var(--color-surface)",
      },
      maxWidth: {
        page: "72rem",
      },
    },
  },
} satisfies Config;
