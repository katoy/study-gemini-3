import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const VITE_PORT = Number(process.env.VITE_PORT || 3010);
const BACKEND_PORT = Number(process.env.PORT || 3011);

export default defineConfig({
  plugins: [react()],
  server: {
    port: VITE_PORT,
    proxy: {
      '/api': {
        target: `http://localhost:${BACKEND_PORT}`,
        changeOrigin: true,
        ws: true,
      },
    },
  },
});
