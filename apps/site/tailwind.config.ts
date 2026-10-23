import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#090d16",
        mist: "#c5d0dc",
        glow: "#67e8f9",
      },
      fontFamily: {
        sans: ["Archivo", "sans-serif"],
      },
      maxWidth: {
        page: "1120px",
      },
    },
  },
} satisfies Config;
