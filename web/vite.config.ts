import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  // Ensure a single React instance (avoids "Invalid hook call" from duplicates).
  resolve: { dedupe: ['react', 'react-dom'] },
  // Dev-only (ignored by `vite build` + tests): the SPA calls /api/... and the vite dev
  // server proxies it to the api service, stripping the /api prefix to match nginx's prod
  // proxy_pass. Only used in the docker dev stack (docker-compose.dev.yml), where the host
  // `api` resolves; local `npm run dev` has no VITE_API_BASE and runs on the in-browser mock.
  server: {
    proxy: {
      '/api': {
        target: 'http://api:8000',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
  },
});
