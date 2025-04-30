import type { Config } from 'tailwindcss'

const config: Config = {
  darkMode: 'class', //
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['var(--font-inter)'],
        serif: ['var(--font-garamond)'],
      },
    },
  },
  plugins: [require('@tailwindcss/typography')],
}

export default config