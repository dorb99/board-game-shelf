import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

const backend = 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { '/api': backend, '/media': backend },
  },
})
