import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { host: '127.0.0.1', proxy: { '/api': 'http://127.0.0.1:8080', '/auth': 'http://127.0.0.1:8080' } },
  build: { sourcemap: false, outDir: 'dist' },
  test: { environment: 'jsdom', setupFiles: './tests/setup.ts', restoreMocks: true },
});
