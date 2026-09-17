/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        ops: {
          bg: "var(--color-ops-bg)",
          panel: "var(--color-ops-panel)",
          "panel-alt": "var(--color-ops-panel-alt)",
          border: "var(--color-ops-border)",
          "border-hover": "var(--color-ops-border-hover)",
          accent: "var(--color-ops-accent)",
          "accent-glow": "var(--color-ops-accent-glow)",
          text: "var(--color-ops-text)",
          "text-muted": "var(--color-ops-text-muted)",
          card: "var(--color-ops-card)",
          surface: "var(--color-ops-surface)",
        },
      },
      fontFamily: {
        sans: ['Plus Jakarta Sans', 'Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Consolas', 'monospace'],
        display: ['Space Grotesk', 'Plus Jakarta Sans', 'sans-serif'],
      },
      boxShadow: {
        'glow-cyan': '0 0 20px -3px rgba(6, 182, 212, 0.45)',
        'glow-emerald': '0 0 20px -3px rgba(16, 185, 129, 0.45)',
        'glow-red': '0 0 20px -3px rgba(239, 68, 68, 0.5)',
        'tactical': '0 10px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1)',
      },
    },
  },
  plugins: [],
}
