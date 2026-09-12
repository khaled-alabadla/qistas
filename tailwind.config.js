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
        navy: { DEFAULT: "#1d4ed8", 50: "#eef4ff", 100: "#dbe7ff", 900: "#132a63" },
        slate: { DEFAULT: "#5b6472" },
        ink: "#101828",
        sand: "#f7f8fa",
        mist: "#f1f4f8",
        line: "#e5e8ee",
        bronze: { DEFAULT: "#b8863b", 700: "#8a6428" },
        danger: "#b3261e",
      },
      fontFamily: {
        sans: ["Cairo", "Segoe UI", "Tahoma", "Arial", "sans-serif"],
      },
      borderRadius: { xl: "0.75rem" },
    },
  },
  plugins: [],
};
