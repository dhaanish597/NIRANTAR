import '@testing-library/jest-dom/vitest'

// jsdom has no ResizeObserver global. MapView.tsx uses a real one to keep MapLibre's canvas sized
// to its container — needed by any test that renders MapView, even with maplibre-gl itself mocked.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
;(globalThis as unknown as { ResizeObserver: typeof ResizeObserverStub }).ResizeObserver = ResizeObserverStub
