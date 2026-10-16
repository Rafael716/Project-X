import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// El build sale a web/dist, que el servidor Node puede servir en producción (ADR-0007).
export default defineConfig({
  plugins: [react()],
  build: { outDir: 'dist' },
});
