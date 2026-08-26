import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'
// vitest/config re-exports vite's defineConfig with the `test` field typed in.
import { defineConfig } from 'vitest/config'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    // BUILD_PLAN.md task 5.1: PWA — service worker via vite-plugin-pwa, app shell cached, install
    // prompt working. This REINFORCES CLAUDE.md rule 10 (demo runs with the network cable
    // unplugged) rather than relaxing it: `generateSW`/`injectManifest` here only precache
    // build-output assets already served from this origin (this app's own JS/CSS/HTML/icons) —
    // MapView's self-contained no-external-tile-requests style (frontend/src/components/
    // MapView.tsx) is untouched, and nothing in this config adds any external network request.
    VitePWA({
      registerType: 'autoUpdate',
      // `injectRegister: 'auto'` (the default) writes the `navigator.serviceWorker.register(...)`
      // call straight into the built `index.html`'s entry script — no manual registration code
      // needed, and nothing to get out of sync with the plugin's own generated file names.
      includeAssets: ['favicon.svg'],
      manifest: {
        name: 'NIRANTAR — NER Landslide Early Warning',
        short_name: 'NIRANTAR',
        description:
          'AI-based early warning and landslide risk monitoring for the North Eastern Region (SIH26001).',
        theme_color: '#0f172a',
        background_color: '#0f172a',
        display: 'standalone',
        start_url: '/',
        icons: [
          { src: 'pwa-192.png', sizes: '192x192', type: 'image/png' },
          { src: 'pwa-512.png', sizes: '512x512', type: 'image/png' },
          { src: 'pwa-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        // Explicit rather than relying on the default glob list — this is what "app shell
        // cached" (task 5.1) means concretely: every build output asset the app needs to render
        // (JS/CSS bundles, the HTML shell, the manifest, icons) is precached, so the app shell
        // paints from cache offline. Scenario/model/tile data under data/ is NOT part of the
        // Vite build output and is out of scope for this task (task 5.2/5.3 own that).
        globPatterns: ['**/*.{js,css,html,svg,png,ico,webmanifest}'],
      },
    }),
  ],
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
  // frontend/src/lib/scenarioDetails.ts reads data/scenarios/*.json (repo root, one level above
  // frontend/) via import.meta.glob so scenario cards (BUILD_PLAN.md task 4.8: name, date, death
  // toll + source note, "held out of training") come from the committed scenario JSON itself
  // rather than a hardcoded frontend fact or a new backend endpoint. Vite's dev-server `/@fs/`
  // serving is restricted to the detected workspace root by default; declare the repo root
  // explicitly so `vite dev`/`vite preview` can serve it (vitest's transform pipeline and
  // production `vite build` both read the filesystem directly and are unaffected either way).
  server: { fs: { allow: [path.resolve(import.meta.dirname, '..')] } },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/setupTests.ts'],
    globals: true,
    // The sandboxed execution environment this project is developed in cannot fork worker
    // processes (vitest's default `forks` pool times out waiting for a worker to respond,
    // 0 tests ever run) — threads work fine since they stay in-process. Harmless outside the
    // sandbox too, just a different concurrency model for the same tests.
    pool: 'threads',
    // Observed one flaky timeout under the full suite's thread-pool contention in this sandbox
    // (a component test that completes in <1s in isolation hit the 5s default) — headroom, not a
    // fix for a real slow test.
    testTimeout: 15000,
  },
})
