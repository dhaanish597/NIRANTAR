import '@testing-library/jest-dom/vitest'
import 'fake-indexeddb/auto'

// jsdom has no ResizeObserver global. MapView.tsx uses a real one to keep MapLibre's canvas sized
// to its container — needed by any test that renders MapView, even with maplibre-gl itself mocked.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
;(globalThis as unknown as { ResizeObserver: typeof ResizeObserverStub }).ResizeObserver = ResizeObserverStub

const originalFetch = globalThis.fetch
if (originalFetch) {
  globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    let resolvedInput = input
    if (typeof input === 'string' && input.startsWith('/')) {
      resolvedInput = `http://localhost:3000${input}`
    }
    try {
      return await originalFetch(resolvedInput, init)
    } catch {
      return new Response(new ArrayBuffer(0), { status: 200 })
    }
  }
}

