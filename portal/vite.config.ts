/// <reference types="vitest" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// GitHub Pages sert le site sous /<repo>/ : la base doit suivre, sinon les
// assets 404. En local (dev, build simple) la base reste '/'.
// Surcharge : VITE_BASE_PATH=/rempart/ npm run build
const basePath = process.env.VITE_BASE_PATH || '/';

export default defineConfig({
  base: basePath,
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/setupTests.ts'
  }
});
