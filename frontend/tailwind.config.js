/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{vue,js,ts,jsx,tsx}"],
  theme: {
    extend: {
      // The primaries are held a step below full saturation so they can be read
      // for hours at a time. `canvas` and `surface` are both white — cards are
      // separated from the page by their ink borders and hard shadows, not by a
      // change of tone — and they stay separate tokens so a future ground
      // colour only has to be set in one of them.
      colors: {
        canvas: "#FFFFFF",
        surface: "#FFFFFF",
        ink: "#141414",
        "bauhaus-red": "#C22B22",
        "bauhaus-blue": "#1A44B8",
        "bauhaus-yellow": "#E0AE1F",
        // Not a Bauhaus primary, and deliberately the only one: green is here
        // to mean "needs nothing from you" on the venue-staff dashboard, where
        // every other status already spends a primary (red blocked, yellow
        // waiting). Held to the same saturation as the three above.
        "bauhaus-green": "#2E7D32",
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
