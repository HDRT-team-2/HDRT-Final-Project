/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        rotem: {
          50: '#F7F7F9',
          100: '#E4E6ED',
          200: '#C0C5D7',
          300: '#919AB7',
          400: '#586593',
          500: '#31447E',
          600: '#0A2369',
          700: '#081C54',
          800: '#06153F',
          900: '#040E2A',
        },
        // Status Colors
        success: {
          50: '#f0fdf4',
          500: '#22c55e',
          600: '#16a34a',
          700: '#15803d',
        },
        warning: {
          50: '#FFF7ED',
          100: '#FFEDD5',
          200: '#FED7AA',
          300: '#FDBA74',
          400: '#FB923C',
          500: '#F97316',
          600: '#EA580C',
          700: '#C2410C',
        },
        danger: {
          50: '#FFF2F2',
          500: '#FF0000',
          600: '#CC0000',
          700: '#990000',
        },
        
      },
    },
  },
  plugins: [],
}