import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
// vitest/config re-exports vite's defineConfig with the `test` field typed in.
import { defineConfig } from 'vitest/config'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Single .env.example lives at the repo root (docs/CLAUDE.md §5 repo layout) — one env file
  // for the whole stack, not a separate one per subproject.
  envDir: path.resolve(import.meta.dirname, '..'),
  // maplibre-gl loads its worker via `new Worker(new URL(..., import.meta.url))`. Vite's esbuild
  // dependency pre-bundler doesn't follow that and emit the worker chunk into
  // node_modules/.vite/deps, so the browser 404s on maplibre-gl-worker.mjs and the map never
  // finishes loading (no error is thrown — it just silently never fires 'load', so nothing
  // painted). Excluding it from pre-bundling serves it as native ESM instead, which resolves the
  // worker URL correctly relative to its real package location.
  optimizeDeps: { exclude: ['maplibre-gl'] },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/setupTests.ts'],
    globals: true,
  },
})
