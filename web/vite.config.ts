import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// Dev: `npm run dev` proxies /api to the local backend (default 8770, đổi bằng
// STUDY_API=http://127.0.0.1:8771 khi chạy bản sao dữ liệu QA).
// Build: base './' so the Python backend can serve web/dist at "/".
const api = process.env.STUDY_API ?? 'http://127.0.0.1:8770';

export default defineConfig({
  base: './',
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: api,
        changeOrigin: true,
        // The backend only accepts same-origin mutations; present the proxied
        // request as coming from the backend's own origin during development.
        configure: (proxy) => {
          proxy.on('proxyReq', (request) => {
            if (request.getHeader('origin')) request.setHeader('origin', api);
          });
        },
      },
    },
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
});
