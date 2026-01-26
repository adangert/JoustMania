import { defineConfig } from 'vite'

export default defineConfig({
  root: 'src',
  build: {
    outDir: '../dist',
    emptyOutDir: true,
    target: 'es2022',  // Support top-level await and modern JS features
  },
  server: {
    port: 5173,
    proxy: {
      // Proxy Connect-Web requests to the connect-proxy service
      '/joustmania': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
    },
  },
})
