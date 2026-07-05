/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        neonRed: '#ff073a',
        vibrantBlue: '#00d4ff',
        darkBg: '#0a0a0a',
        panel: '#1a1a1a',
        border: '#333333',
      },
    },
  },
  plugins: [],
}
