import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './lib/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // Aviation-ops palette: neutral slate base with a single teal accent.
        // Final tokens land in U9 alongside the design pass.
        accent: {
          DEFAULT: '#0d9488', // teal-600
          fg: '#f0fdfa', // teal-50
          muted: '#134e4a', // teal-900
        },
      },
      fontFamily: {
        sans: ['var(--font-sans)', 'system-ui', 'sans-serif'],
        mono: ['var(--font-mono)', 'ui-monospace', 'monospace'],
      },
    },
  },
  plugins: [],
};

export default config;
