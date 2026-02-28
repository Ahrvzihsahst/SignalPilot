/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        profit: { DEFAULT: '#16a34a', light: '#dcfce7' },
        loss: { DEFAULT: '#dc2626', light: '#fef2f2' },
        strategy: {
          gap: '#3b82f6',
          orb: '#8b5cf6',
          vwap: '#06b6d4',
          reserve: '#9ca3af',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
    },
  },
  plugins: [],
};
