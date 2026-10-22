/** @type {import('tailwindcss').Config} */
const preset = {
  theme: {
    extend: {
      colors: {
        // Driven by the --primary-* variables in tokens.css so the portal can re-theme at runtime.
        accent: {
          DEFAULT: "rgb(var(--primary-rgb) / <alpha-value>)",
          hover: "rgb(var(--primary-hover-rgb) / <alpha-value>)",
        },
        // Same token under its canonical name; shared @ai-pos/ui components use `primary` so they read the same in
        // the portal and the register (which extends it with a full shade scale).
        primary: {
          DEFAULT: "rgb(var(--primary-rgb) / <alpha-value>)",
          hover: "rgb(var(--primary-hover-rgb) / <alpha-value>)",
        },
        neutral: "#CBCECE",
        canvas: "#EAEAEA",
        line: "#DBDBDB",
        charcoal: "#222026",
        card: "#FFFFFF",
        surface: "#F3F4F6",
      },
      fontFamily: {
        sans: ["Archivo", "sans-serif"],
      },
      borderRadius: {
        card: "20px",
      },
    },
  },
};

export default preset;
