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
        },
      },
    },
  },
  plugins: [],
};
