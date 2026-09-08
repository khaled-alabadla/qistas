/** Qistas Tailwind config — logical utilities only, no RTL plugin (docs/adr/0024). */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./*/templates/**/*.html",
    "./*/**/templates/**/*.html",
    "./core/**/*.py",
  ],
  theme: {
    extend: {
      colors: {
        navy: { DEFAULT: "#0f1f3d", 900: "#0b1730" },
        slate: { DEFAULT: "#3f4b5b" },
        ink: "#1c2430",
        sand: "#f6f3ec",
        mist: "#eef1f5",
        line: "#e2e6ec",
        bronze: { DEFAULT: "#b8863b", 700: "#8a6428" },
        danger: "#b3261e",
      },
      fontFamily: {
        sans: [
          "IBM Plex Sans Arabic",
          "Segoe UI",
          "Tahoma",
          "Arial",
          "sans-serif",
        ],
      },
      borderRadius: { xl: "0.9rem" },
    },
  },
  plugins: [],
};
