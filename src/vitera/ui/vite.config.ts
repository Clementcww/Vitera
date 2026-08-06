import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// `base: './'` so the built bundle runs from any path — including
// `python -m http.server` in the repo root, which is what `make demo-offline`
// uses. No CDN, no absolute origin: a demo that needs the network is a demo
// that can fail on stage.
export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    outDir: 'dist',
    assetsInlineLimit: 0,
    rollupOptions: {
      output: {
        manualChunks(id) {
          // three.js is the one dependency that can take the demo down on an
          // unknown GPU. Keeping it in its own chunk means the workbench
          // parses and renders before WebGL is ever touched.
          if (id.includes('three') || id.includes('@react-three')) return 'three'
        },
      },
    },
  },
})
