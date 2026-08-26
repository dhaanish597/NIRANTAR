import { readFileSync } from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

/**
 * BUILD_PLAN.md task 5.1 (PWA). `vite-plugin-pwa`'s actual output (service worker registration,
 * manifest content, precache list) is proven for real by a production build + a real browser
 * check — see this agent's final report for the exact evidence (a `vite build` producing
 * dist/sw.js + dist/manifest.webmanifest + dist/registerSW.js, and a headless-browser check that
 * `navigator.serviceWorker.getRegistrations()` returns a real active registration against the
 * built preview server). jsdom (this project's vitest environment) does not implement
 * ServiceWorker at all, so that check cannot live here as a vitest test — this file instead
 * guards the two things that CAN regress silently between such manual verifications: the icon
 * files vite.config.ts's manifest points at actually exist and are valid, and the config's PWA
 * block hasn't been quietly deleted.
 */

const FRONTEND_ROOT = import.meta.dirname

function readPngDimensions(filePath: string): { width: number; height: number } {
  const buffer = readFileSync(filePath)
  const pngSignature = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])
  if (!buffer.subarray(0, 8).equals(pngSignature)) {
    throw new Error(`${filePath} is not a valid PNG (bad signature).`)
  }
  // IHDR is always the first chunk: 4-byte length, 4-byte type "IHDR", then width/height as two
  // big-endian uint32s.
  const width = buffer.readUInt32BE(16)
  const height = buffer.readUInt32BE(20)
  return { width, height }
}

describe('PWA icons referenced by vite.config.ts', () => {
  it('pwa-192.png exists, is a valid PNG, and is actually 192x192', () => {
    const dims = readPngDimensions(path.join(FRONTEND_ROOT, 'public', 'pwa-192.png'))
    expect(dims).toEqual({ width: 192, height: 192 })
  })

  it('pwa-512.png exists, is a valid PNG, and is actually 512x512 (used for both "any" and "maskable")', () => {
    const dims = readPngDimensions(path.join(FRONTEND_ROOT, 'public', 'pwa-512.png'))
    expect(dims).toEqual({ width: 512, height: 512 })
  })
})

describe('vite.config.ts PWA configuration', () => {
  const configSource = readFileSync(path.join(FRONTEND_ROOT, 'vite.config.ts'), 'utf-8')

  it('registers the VitePWA plugin', () => {
    expect(configSource).toMatch(/VitePWA\(/)
  })

  it('declares a manifest with the app name, theme colours, and all three real icon entries', () => {
    expect(configSource).toMatch(/name:\s*'NIRANTAR/)
    expect(configSource).toMatch(/theme_color:\s*'#0f172a'/)
    expect(configSource).toMatch(/pwa-192\.png/)
    expect(configSource).toMatch(/pwa-512\.png/)
    expect(configSource).toMatch(/purpose:\s*'maskable'/)
  })

  it('keeps the maplibre-gl optimizeDeps exclusion (the documented worker-chunk fix) intact', () => {
    // Regression guard: this agent's task brief explicitly warns not to remove this while
    // touching build config.
    expect(configSource).toMatch(/exclude:\s*\['maplibre-gl'\]/)
  })
})
