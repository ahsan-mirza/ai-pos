import preset from "@ai-pos/design-tokens/tailwind-preset";
import type { Config } from "tailwindcss";

export default {
  presets: [preset as Config],
  content: ["./index.html", "./src/**/*.{ts,tsx}", "../../packages/ui/src/**/*.{ts,tsx}"],
  // The portal is light-only; shared @ai-pos/ui components carry `dark:` variants for the register, which never apply here.
  darkMode: "class",
} satisfies Config;
