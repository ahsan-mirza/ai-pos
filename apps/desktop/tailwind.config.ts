import preset from "@ai-pos/design-tokens/tailwind-preset";
import type { Config } from "tailwindcss";

const channel = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;
const primaryScale = {
  DEFAULT: channel("primary-rgb"),
  hover: channel("primary-hover-rgb"),
  ...Object.fromEntries([50, 100, 200, 300, 400, 500, 600, 700].map((step) => [step, channel(`primary-${step}-rgb`)])),
};

export default {
  presets: [preset as Config],
  content: ["./index.html", "./src/**/*.{ts,tsx}", "../../packages/ui/src/**/*.{ts,tsx}"],
  darkMode: [
    "variant",
    [
      '&:where(.dark, .dark *, [data-theme="dark"], [data-theme="dark"] *)',
      '@media (prefers-color-scheme: dark) { &:where([data-theme="system"], [data-theme="system"] *) }',
    ],
  ],
  theme: {
    extend: {
      colors: {
        // The register's single accent, set in POS Settings → Primary Accent Color (src/lib/theme.ts).
        // `accent` and `orange` are aliases of `primary` so no class can drift from the chosen color.
        primary: primaryScale,
        accent: primaryScale,
        orange: primaryScale,
        zinc: { 900: "#121215" },
        ink: {
          DEFAULT: "#121214",
          panel: "#1a1a1e",
          raised: "#222227",
          line: "#2c2c33",
        },
      },
    },
  },
} satisfies Config;
