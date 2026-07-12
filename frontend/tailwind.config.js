/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        accent: {
          DEFAULT: "#7c9eff",
          dim: "#4b5fa8",
          bright: "#a8c0ff",
        },
      },
      keyframes: {
        "orb-breathe": {
          "0%, 100%": { transform: "scale(1)", opacity: "0.75" },
          "50%": { transform: "scale(1.08)", opacity: "1" },
        },
        "orb-think": {
          "0%, 100%": { transform: "scale(1) rotate(0deg)", opacity: "0.85" },
          "50%": { transform: "scale(1.14)", opacity: "1" },
          "100%": { transform: "scale(1) rotate(360deg)", opacity: "0.85" },
        },
        "orb-listen": {
          "0%, 100%": { transform: "scale(1)" },
          "50%": { transform: "scale(1.22)" },
        },
        "orb-speak": {
          "0%, 100%": { transform: "scaleY(1)" },
          "20%": { transform: "scaleY(1.3)" },
          "40%": { transform: "scaleY(0.85)" },
          "60%": { transform: "scaleY(1.2)" },
          "80%": { transform: "scaleY(0.95)" },
        },
        "ring-ripple": {
          "0%": { transform: "scale(0.9)", opacity: "0.5" },
          "100%": { transform: "scale(1.9)", opacity: "0" },
        },
        "ambient-drift": {
          "0%, 100%": { transform: "translate(0, 0) scale(1)" },
          "33%": { transform: "translate(2%, -3%) scale(1.05)" },
          "66%": { transform: "translate(-2%, 2%) scale(0.98)" },
        },
      },
      animation: {
        "orb-breathe": "orb-breathe 4.5s ease-in-out infinite",
        "orb-think": "orb-think 2.2s ease-in-out infinite",
        "orb-listen": "orb-listen 1.1s ease-in-out infinite",
        "orb-speak": "orb-speak 0.9s ease-in-out infinite",
        "ring-ripple": "ring-ripple 1.8s ease-out infinite",
        "ambient-drift": "ambient-drift 22s ease-in-out infinite",
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};
