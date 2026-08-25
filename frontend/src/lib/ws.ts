import type { TickResult } from '../types/schemas'

const WS_URL = import.meta.env.VITE_WS_URL ?? 'ws://localhost:8000/ws/ticks'

export type WsStatus = 'connecting' | 'open' | 'closed'

export interface TickSocketHandlers {
  onTick: (tick: TickResult) => void
  onStatusChange?: (status: WsStatus) => void
}

const RECONNECT_DELAYS_MS = [500, 1000, 2000, 5000] // capped backoff; demo shouldn't die on a blip

/** Connects to /ws/ticks and auto-reconnects on close (a judge's demo dropping one frame of
 * WebSocket should not end the demo). Returns a cleanup function that stops reconnecting and
 * closes the socket. */
export function connectTickSocket({ onTick, onStatusChange }: TickSocketHandlers): () => void {
  let socket: WebSocket | null = null
  let attempt = 0
  let stopped = false
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null

  const connect = () => {
    if (stopped) return
    onStatusChange?.('connecting')
    socket = new WebSocket(WS_URL)

    socket.onopen = () => {
      attempt = 0
      onStatusChange?.('open')
    }

    socket.onmessage = (event: MessageEvent<string>) => {
      const tick = JSON.parse(event.data) as TickResult
      onTick(tick)
    }

    socket.onclose = () => {
      onStatusChange?.('closed')
      if (stopped) return
      const delay = RECONNECT_DELAYS_MS[Math.min(attempt, RECONNECT_DELAYS_MS.length - 1)]
      attempt += 1
      reconnectTimer = setTimeout(connect, delay)
    }

    socket.onerror = () => {
      socket?.close()
    }
  }

  connect()

  return () => {
    stopped = true
    if (reconnectTimer) clearTimeout(reconnectTimer)
    socket?.close()
  }
}
