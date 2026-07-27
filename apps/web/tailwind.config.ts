import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          "\"Segoe UI\"",
          "system-ui",
          "sans-serif"
        ],
        mono: ["\"SFMono-Regular\"", "Consolas", "\"Liberation Mono\"", "monospace"]
      },
      colors: {
        truss: {
          base: "oklch(0.973 0.006 260)",
          panel: "oklch(0.997 0.003 260)",
          raised: "oklch(0.985 0.004 260)",
          canvas: "oklch(0.943 0.006 260)",
          line: "oklch(0.875 0.009 260)",
          text: "oklch(0.205 0.015 260)",
          muted: "oklch(0.49 0.018 260)",
          subtle: "oklch(0.68 0.015 260)",
          accent: "oklch(0.58 0.17 255)",
          accentSoft: "oklch(0.94 0.035 255)",
          success: "oklch(0.58 0.13 155)",
          danger: "oklch(0.58 0.18 25)",
          warning: "oklch(0.66 0.13 78)"
        }
      }
    }
  },
  plugins: []
};

export default config;
