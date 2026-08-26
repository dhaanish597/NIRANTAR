import type { Announcement, TickResult } from '../types/schemas'

const WS_URL = import.meta.env.VITE_WS_URL ?? 'ws://localhost:8000/ws/ticks'

export type WsStatus = 'connecting' | 'open' | 'closed'

export interface TickSocketHandlers {
  onTick: (tick: TickResult) => void
  onAnnouncement?: (announcement: Announcement) => void
  onStatusChange?: (status: WsStatus) => void
}

const RECONNECT_DELAYS_MS = [500, 1000, 2000, 5000] // capped backoff; demo shouldn't die on a blip

/** Connects to /ws/ticks and auto-reconnects on close. Multiplexes two message shapes off the
 * same connection: a bare TickResult (no `type` field), or `{type: "announcement", data:
 * Announcement}` — see backend/app/ws/hub.py's matching wrapper. */
export function connectTickSocket({
  onTick,
  onAnnouncement,
  onStatusChange,
}: TickSocketHandlers): () => void {
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
      const parsed = JSON.parse(event.data) as TickResult | { type: 'announcement'; data: Announcement }
      if ('type' in parsed && parsed.type === 'announcement') {
        onAnnouncement?.(parsed.data)
      } else {
        onTick(parsed as TickResult)
      }
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
