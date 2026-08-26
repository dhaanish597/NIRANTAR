import { describe, expect, it, vi } from 'vitest'
import { connectTickSocket } from './ws'

class FakeWebSocket {
  static instances: FakeWebSocket[] = []
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  close = vi.fn()
  constructor() {
    FakeWebSocket.instances.push(this)
  }
  emitMessage(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) })
  }
}

describe('connectTickSocket', () => {
  it('routes a bare TickResult message to onTick', () => {
    vi.stubGlobal('WebSocket', FakeWebSocket)
    const onTick = vi.fn()
    const onAnnouncement = vi.fn()
    connectTickSocket({ onTick, onAnnouncement })
    const socket = FakeWebSocket.instances[FakeWebSocket.instances.length - 1]
    socket.emitMessage({ t: '2026-01-01T00:00:00+05:30', mode: 'live', aoi_id: 'aizawl', cell_risks: [] })
    expect(onTick).toHaveBeenCalledTimes(1)
    expect(onAnnouncement).not.toHaveBeenCalled()
  })

  it('routes a {type: "announcement"} message to onAnnouncement, not onTick', () => {
    vi.stubGlobal('WebSocket', FakeWebSocket)
    const onTick = vi.fn()
    const onAnnouncement = vi.fn()
    connectTickSocket({ onTick, onAnnouncement })
    const socket = FakeWebSocket.instances[FakeWebSocket.instances.length - 1]
    socket.emitMessage({ type: 'announcement', data: { id: 'ann-1', alert_id: 'a1' } })
    expect(onAnnouncement).toHaveBeenCalledWith({ id: 'ann-1', alert_id: 'a1' })
    expect(onTick).not.toHaveBeenCalled()
  })
})
