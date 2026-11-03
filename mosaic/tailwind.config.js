import defaultTheme from "tailwindcss/defaultTheme";

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./src/**/*.{html,jsx,tsx,vue,js,ts}"],
  theme: {
    extend: {
      // Japanese first, so kana and kanji do not fall back to a Chinese face; Chinese and Korean after it
      fontFamily: {
        sans: [
          '"Noto Sans JP"',
          '"Noto Sans SC"',
          '"Noto Sans KR"',
          '"Hiragino Kaku Gothic ProN"',
          '"Yu Gothic"',
          "Meiryo",
          '"Microsoft YaHei"',
          '"Malgun Gothic"',
          ...defaultTheme.fontFamily.sans,
        ],
      },
      spacing: {
        '28': '28px', // Define a custom margin-top value
      },
    },
  },
  plugins: [],
}

