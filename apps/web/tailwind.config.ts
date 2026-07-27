import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-geist-sans)", "Arial", "sans-serif"],
        mono: ["var(--font-geist-mono)", "Consolas", "monospace"]
      },
      colors: {
        truss: {
          base: "oklch(0.135 0.006 25)",
          panel: "oklch(0.18 0.008 25)",
          line: "oklch(0.31 0.011 25)",
          text: "oklch(0.9 0.008 40)",
          muted: "oklch(0.67 0.009 40)",
          accent: "oklch(0.62 0.22 29)"
        }
      }
    }
  },
  plugins: []
};

export default config;
