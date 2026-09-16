/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{vue,js,ts,jsx,tsx}"],
  theme: {
    extend: {
      // The primaries are held a step below full saturation so they can be read
      // for hours at a time, and `surface` gives cards a ground of their own so
      // they no longer need a colour fill just to separate from the canvas.
      colors: {
        canvas: "#EFEEEA",
        surface: "#FFFFFF",
        ink: "#141414",
        "bauhaus-red": "#C22B22",
        "bauhaus-blue": "#1A44B8",
        "bauhaus-yellow": "#E0AE1F",
        muted: "#E4E2DC",
      },
      fontFamily: {
        sans: ["Outfit", "sans-serif"],
      },
      boxShadow: {
        hard: "4px 4px 0px 0px #141414",
        "hard-lg": "8px 8px 0px 0px #141414",
      },
      borderRadius: {
        none: "0px",
        full: "9999px",
      },
    },
  },
  plugins: [],
};
