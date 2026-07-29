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
          base: "#0e0f10",
          panel: "#17191b",
          panel2: "#1d2022",
          raised: "#141618",
          canvas: "#101213",
          line: "#2a2e31",
          grid: "#202426",
          text: "#e7eaeb",
          muted: "#98a0a5",
          subtle: "#79838a",
          accent: "#d93b2b",
          accentSoft: "#3a1512",
          danger: "#ff4a37",
          warning: "#dfa03c",
          success: "#3fa860",
          info: "#6f8ea3",
          sheet: "#f2f0ec"
        }
      },
      borderRadius: {
        truss: "4px"
      },
      boxShadow: {
        "truss-red": "0 0 0 1px rgba(217,59,43,0.5), 0 0 24px rgba(217,59,43,0.18)",
        "truss-panel": "0 12px 34px rgba(0,0,0,0.45)"
      }
    }
  },
  plugins: []
};

export default config;
