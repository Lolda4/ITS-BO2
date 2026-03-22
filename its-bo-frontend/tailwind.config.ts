import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        "lab-bg":      "#0B0E14",
        "lab-surface": "#131720",
        "lab-card":    "#1A1F2E",
        "lab-border":  "#252B3B",
        "lab-text":    "#E2E8F0",
        "lab-muted":   "#64748B",
        primary:       "#3B82F6",
        "primary-dim": "#2563EB",
        pass:          "#22C55E",
        "pass-dim":    "#166534",
        fail:          "#EF4444",
        "fail-dim":    "#991B1B",
        warn:          "#F59E0B",
        "warn-dim":    "#92400E",
      },
      fontFamily: {
        mono: ["GeistMono", "JetBrains Mono", "Fira Code", "monospace"],
        sans: ["Inter", "Geist", "system-ui", "sans-serif"],
      },
      animation: {
        "pulse-live": "pulse-live 2s ease-in-out infinite",
        "fade-in":    "fade-in 0.3s ease-out",
        "slide-up":   "slide-up 0.3s ease-out",
      },
      keyframes: {
        "pulse-live": {
          "0%, 100%": { opacity: "1" },
          "50%":      { opacity: "0.5" },
        },
        "fade-in": {
          "0%":   { opacity: "0" },
          "100%": { opacity: "1" },
        },
        "slide-up": {
          "0%":   { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
    },
  },
  plugins: [],
};
export default config;
