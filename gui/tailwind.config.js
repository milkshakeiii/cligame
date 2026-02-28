/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        space: {
          bg: "#0a0a12",
          panel: "#0d1117",
          border: "#1a3a5c",
        },
        text: {
          primary: "#c9d1d9",
          secondary: "#8b949e",
        },
        solarion: "#d4a843",
        voidborn: "#7b4bb5",
        friendly: "#4488cc",
        hostile: "#cc4444",
        shield: "#4488ff",
        armor: "#cc8833",
        cap: "#66aaff",
        "cap-depleted": "#ff3333",
        "module-active": "#33cc66",
        "alert-warn": "#e68a00",
        "alert-crit": "#ff2222",
        "alert-info": "#3388cc",
        "alert-ok": "#33aa55",
      },
      fontFamily: {
        mono: [
          "JetBrains Mono",
          "Fira Code",
          "Cascadia Code",
          "monospace",
        ],
      },
    },
  },
  plugins: [],
};
