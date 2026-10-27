import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // Proxy preview container ports through Vite for iframe embedding
      '/preview-proxy': {
        target: 'https://stg-dsuite-backend.bourntec.com',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/preview-proxy/, '/agents/preview/proxy'),
      },
    },
  },
  preview: {
    host: '0.0.0.0',
    port: 5172,
    allowedHosts: ['stg-dsuite.bourntec.com', 'stg-dsuite-backend.bourntec.com']
  }
})

