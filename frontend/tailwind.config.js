/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        border: 'hsl(var(--border) / <alpha-value>)',
        input: 'hsl(var(--input) / <alpha-value>)',
        ring: 'hsl(var(--ring) / <alpha-value>)',
        background: 'hsl(var(--background) / <alpha-value>)',
        foreground: 'hsl(var(--foreground) / <alpha-value>)',
        primary: {
          DEFAULT: 'hsl(var(--primary) / <alpha-value>)',
          foreground: 'hsl(var(--primary-foreground) / <alpha-value>)',
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary) / <alpha-value>)',
          foreground: 'hsl(var(--secondary-foreground) / <alpha-value>)',
        },
        muted: {
          DEFAULT: 'hsl(var(--muted) / <alpha-value>)',
          foreground: 'hsl(var(--muted-foreground) / <alpha-value>)',
        },
        accent: {
          DEFAULT: 'hsl(var(--accent) / <alpha-value>)',
          foreground: 'hsl(var(--accent-foreground) / <alpha-value>)',
        },
        destructive: {
          DEFAULT: 'hsl(var(--destructive) / <alpha-value>)',
          foreground: 'hsl(var(--destructive-foreground) / <alpha-value>)',
        },
        // CollectUI-inspired Ocean Teal brand scale
        brand: {
          50: '#edfaf7',
          100: '#d2f4ec',
          200: '#a7e9db',
          300: '#6fd7c3',
          400: '#35bea7',
          500: '#0f9d8a',
          600: '#0d8274',
          700: '#0b685e',
          800: '#0d534c',
          900: '#0f4540',
          950: '#062926',
        },
        // Warm Coral accent for energetic CollectUI highlights
        coral: {
          50: '#fff4f2',
          100: '#ffe5e0',
          200: '#ffcfc6',
          300: '#ffae9f',
          400: '#fb7f69',
          500: '#f25c43',
          600: '#df4127',
          700: '#bc331d',
        },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        display: [
          'Plus Jakarta Sans',
          'Inter',
          'ui-sans-serif',
          'system-ui',
          'sans-serif',
        ],
      },
      boxShadow: {
        card: '0 1px 2px rgba(15, 23, 42, 0.03), 0 6px 20px -10px rgba(15, 23, 42, 0.08)',
        'card-hover':
          '0 12px 32px -12px rgba(13, 130, 116, 0.16), 0 4px 12px -4px rgba(15, 23, 42, 0.06)',
        glow: '0 10px 26px -10px rgba(15, 157, 138, 0.55)',
        float: '0 4px 14px -2px rgba(15, 23, 42, 0.12), 0 2px 6px -2px rgba(15, 23, 42, 0.06)',
      },
      keyframes: {
        'fade-in': {
          from: { opacity: '0', transform: 'translateY(8px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        'fade-up': {
          from: { opacity: '0', transform: 'translateY(14px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        'scale-in': {
          from: { opacity: '0', transform: 'scale(0.96)' },
          to: { opacity: '1', transform: 'scale(1)' },
        },
        'slide-in-left': {
          from: { opacity: '0', transform: 'translateX(-10px)' },
          to: { opacity: '1', transform: 'translateX(0)' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%': { transform: 'translateY(-8px)' },
        },
        'bar-grow': {
          from: { transform: 'scaleX(0)', transformOrigin: 'left' },
          to: { transform: 'scaleX(1)', transformOrigin: 'left' },
        },
        shimmer: {
          from: { transform: 'translateX(-100%)' },
          to: { transform: 'translateX(100%)' },
        },
        dash: {
          to: { strokeDashoffset: '-20' },
        },
        'pulse-soft': {
          '0%, 100%': { opacity: '0.45', transform: 'scale(1)' },
          '50%': { opacity: '0.18', transform: 'scale(1.12)' },
        },
      },
      animation: {
        'fade-in': 'fade-in 0.42s cubic-bezier(0.16, 1, 0.3, 1) both',
        'fade-up': 'fade-up 0.5s cubic-bezier(0.16, 1, 0.3, 1) both',
        'scale-in': 'scale-in 0.32s cubic-bezier(0.16, 1, 0.3, 1) both',
        'slide-in-left': 'slide-in-left 0.35s cubic-bezier(0.16, 1, 0.3, 1) both',
        float: 'float 6s ease-in-out infinite',
        'bar-grow': 'bar-grow 0.7s cubic-bezier(0.16, 1, 0.3, 1) both',
        shimmer: 'shimmer 1.6s infinite',
        dash: 'dash 0.8s linear infinite',
        'pulse-soft': 'pulse-soft 3.4s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
