import fs from 'node:fs'
import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import type { Plugin } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'
// vitest/config re-exports vite's defineConfig with the `test` field typed in.
import { defineConfig } from 'vitest/config'

function offlineAssetManifestEntries() {
  const tilesDir = path.resolve(import.meta.dirname, '../data/tiles')
  if (!fs.existsSync(tilesDir)) return []
  return fs.readdirSync(tilesDir).flatMap((name) => {
    const url = name.endsWith('.pmtiles')
      ? `/tiles/${name}`
      : name.endsWith('-hillshade.png')
        ? `/terrain/${name}`
        : null
    if (!url) return []
    const stat = fs.statSync(path.join(tilesDir, name))
    return [{ url, revision: `${stat.size}-${Math.trunc(stat.mtimeMs)}` }]
  })
}

// BUILD_PLAN.md task 5.2: serves data/tiles/*.pmtiles (built by scripts/build_tiles.py, gitignored
// per CLAUDE.md rule 15 — same "produced by scripts/, never committed" status as data/osm/*.pkl)
// at same-origin `/tiles/<name>.pmtiles`, in BOTH `vite dev` and a real `vite build` + static
// serve of `dist/`. Same-origin, not a remote tile host — CLAUDE.md rule 10 unchanged.
//
// A plain static-file copy/serve, not import.meta.glob (used elsewhere in this file for
// data/scenarios/*.json): a .pmtiles archive is a large binary the browser fetches lazily as raw
// bytes (frontend/src/lib/offlineTiles.ts), not something to inline into a JS bundle.
//
// Not placed under frontend/public/tiles/ (Vite's normal static-asset dir): public/ assets are
// committed to git by default, and a multi-MB .pmtiles archive is exactly the "never commit large
// binaries" case CLAUDE.md rule 15 exists for — data/tiles/ stays gitignored and canonical, this
// plugin only ever copies/serves FROM it, never duplicates it into a tracked location.
function offlineTilesPlugin(): Plugin {
  const tilesDir = path.resolve(import.meta.dirname, '../data/tiles')

  return {
    name: 'nirantar-serve-offline-tiles',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const prefix = req.url?.startsWith('/tiles/')
          ? '/tiles/'
          : req.url?.startsWith('/terrain/')
            ? '/terrain/'
            : null
        if (!prefix) return next()
        const requested = decodeURIComponent(req.url!.slice(prefix.length))
        // Reject path traversal / nested paths outright — this only ever serves a flat
        // <aoi>.pmtiles file directly out of data/tiles/, nothing else.
        const allowed = prefix === '/tiles/' ? /^[\w-]+\.pmtiles$/ : /^[\w-]+-hillshade\.png$/
        if (!allowed.test(requested)) return next()
        const filePath = path.join(tilesDir, requested)
        if (!fs.existsSync(filePath)) return next()
        res.setHeader('Content-Type', requested.endsWith('.png') ? 'image/png' : 'application/octet-stream')
        fs.createReadStream(filePath).pipe(res)
      })
    },
    closeBundle() {
      if (!fs.existsSync(tilesDir)) return
      const outDir = path.resolve(import.meta.dirname, 'dist/tiles')
      const terrainDir = path.resolve(import.meta.dirname, 'dist/terrain')
      fs.mkdirSync(outDir, { recursive: true })
      fs.mkdirSync(terrainDir, { recursive: true })
      for (const name of fs.readdirSync(tilesDir)) {
        if (name.endsWith('.pmtiles')) fs.copyFileSync(path.join(tilesDir, name), path.join(outDir, name))
        if (name.endsWith('-hillshade.png')) fs.copyFileSync(path.join(tilesDir, name), path.join(terrainDir, name))
      }
    },
  }
}

// Bug found and fixed while REALLY verifying task 5.2's "must render with the network disabled"
// DoD (a real `vite build` + `vite preview` + Playwright check with the network actually
// disabled, not just `vite dev`, which task 5.1's own verification used) — pre-existing, not
// introduced by this session's task-5.2 changes, but it broke the offline reference layer's own
// verification so it's fixed here rather than left standing.
//
// maplibre-gl v6 loads its worker via `new Worker(new URL('maplibre-gl-worker.mjs',
// import.meta.url))`. In `vite dev`, `optimizeDeps: { exclude: ['maplibre-gl'] }` above (an
// EARLIER session's fix, see its own comment) makes this resolve correctly. In a real `vite
// build`, maplibre-gl's source is inlined into the main JS chunk rather than kept as a separate
// module, so `import.meta.url` at runtime resolves to that chunk's own URL
// (`/assets/index-<hash>.js`) and the computed worker URL becomes the literal, unhashed
// `/assets/maplibre-gl-worker.mjs` — a file `vite build` never emits on its own. Confirmed for
// real: that request returned HTTP 200 with `vite preview`'s SPA-fallback `index.html` content
// (wrong content, not a 404) instead of erroring loudly, silently breaking every worker-dependent
// render path (GeoJSON AND vector-tile sources alike — not just this task's new PMTiles layer).
// The worker script itself then imports a SECOND real file the same way — `maplibre-gl-
// shared.mjs` — confirmed by the same "200 with the wrong index.html content" symptom re-
// appearing for it too once the first file was fixed. Rather than hardcode exactly two filenames
// and risk a THIRD one surfacing the same way in a future maplibre-gl upgrade, this copies every
// non-"-dev" `.mjs` file maplibre-gl's own package ships in `dist/` — real build output the
// package publishes for exactly this deployment need, not guessed filenames.
function copyMaplibreWorkerPlugin(): Plugin {
  const srcDir = path.resolve(import.meta.dirname, 'node_modules/maplibre-gl/dist')
  return {
    name: 'nirantar-copy-maplibre-worker',
    closeBundle() {
      if (!fs.existsSync(srcDir)) return
      const outDir = path.resolve(import.meta.dirname, 'dist/assets')
      fs.mkdirSync(outDir, { recursive: true })
      for (const name of fs.readdirSync(srcDir)) {
        if (!name.endsWith('.mjs') || name.includes('-dev')) continue
        fs.copyFileSync(path.join(srcDir, name), path.join(outDir, name))
      }
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    offlineTilesPlugin(),
    // Must run its closeBundle copy BEFORE VitePWA's below, so the worker file exists in dist/
    // when VitePWA scans dist/ to build the precache manifest (workbox globPatterns' new '.mjs'
    // entry, below, only picks it up if it's already on disk at that point).
    copyMaplibreWorkerPlugin(),
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
        // `mjs` added this session (task 5.2 verification) — copyMaplibreWorkerPlugin above
        // copies maplibre-gl's real worker script into dist/assets/ as a genuine build output
        // file; without `mjs` in this list it would never enter the precache manifest and every
        // worker-dependent map render (this task's offline layer included) would silently break
        // the moment the app is opened fully offline, even after a first successful online visit.
        globPatterns: ['**/*.{js,mjs,css,html,svg,png,ico,webmanifest}'],
        additionalManifestEntries: offlineAssetManifestEntries(),
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
