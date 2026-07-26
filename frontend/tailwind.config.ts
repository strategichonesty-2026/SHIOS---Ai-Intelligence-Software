import type { Config } from "tailwindcss";

/**
 * Palette: an instrument panel, not a marketing page. Cool graphite paper, a single
 * evidence-teal for anything the system can prove, amber for anything provisional,
 * and rose reserved exclusively for governance failures.
 */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#EEF1F4",
        surface: "#FFFFFF",
        ink: "#0D1B2A",
        muted: "#5B6B7B",
        line: "#D3DAE1",
        proof: "#0F766E",
        proofSoft: "#D7EDEA",
        provisional: "#B45309",
        provisionalSoft: "#FBEBD7",
        fail: "#9F1239",
        failSoft: "#F9DDE4",
      },
      fontFamily: {
        display: ["'Space Grotesk'", "ui-sans-serif", "system-ui", "sans-serif"],
        body: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["'JetBrains Mono'", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      fontSize: {
        eyebrow: ["0.6875rem", { lineHeight: "1rem", letterSpacing: "0.14em" }],
      },
      borderRadius: { card: "3px" },
    },
  },
  plugins: [],
};

export default config;
