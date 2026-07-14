import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Em `npm run dev`, /api e proxiado para o backend local (porta 8010).
// Em producao, o nginx serve o build e faz o mesmo proxy (doc 13).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8010',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
})
