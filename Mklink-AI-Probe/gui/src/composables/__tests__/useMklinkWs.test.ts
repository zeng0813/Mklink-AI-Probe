import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

vi.stubGlobal('import.meta', { env: { VITE_MKLINK_WS: '' } })
vi.stubGlobal('location', { protocol: 'http:', host: 'localhost:5173' })

import { useMklinkWs } from '../useMklinkWs'

class MockWebSocket {
  static OPEN = 1
  static CLOSED = 3
  readyState = MockWebSocket.OPEN
  onopen: (() => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  onmessage: ((ev: { data: string }) => void) | null = null
  sent: string[] = []
  closed = false

  constructor(public url: string) {}

  send(data: string) { this.sent.push(data) }
  close() {
    this.closed = true
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.()
  }
}

describe('useMklinkWs', () => {
  let ws: MockWebSocket

  beforeEach(() => {
    const OrigMock = class extends MockWebSocket {
      constructor(url: string) {
        super(url)
        ws = this
      }
    }
    vi.stubGlobal('WebSocket', OrigMock)
  })

  afterEach(() => {
    try { useMklinkWs().disconnect() } catch {}
    vi.restoreAllMocks()
  })

  it('connect sets wsConnected to true', () => {
    const { connect, wsConnected } = useMklinkWs()
    connect(undefined, 'ws://localhost')
    ws.onopen!()
    expect(wsConnected.value).toBe(true)
  })

  it('duplicate connect does not create new WebSocket', () => {
    const { connect } = useMklinkWs()
    connect(undefined, 'ws://localhost')
    ws.onopen!()
    const first = ws
    connect(undefined, 'ws://localhost')
    expect(first).toBe(ws)
  })

  it('disconnect clears pending and sets connected false', () => {
    const { connect, disconnect, wsConnected, rpc } = useMklinkWs()
    connect(undefined, 'ws://localhost')
    ws.onopen!()
    const p = rpc('test')
    disconnect()
    expect(wsConnected.value).toBe(false)
    expect(p).rejects.toThrow('WebSocket closed')
  })

  it('rpc sends JSON-RPC and resolves on response', async () => {
    const { connect, rpc } = useMklinkWs()
    connect(undefined, 'ws://localhost')
    ws.onopen!()

    const p = rpc('method', { a: 1 })
    const sent = JSON.parse(ws.sent[0])
    expect(sent.jsonrpc).toBe('2.0')
    expect(sent.method).toBe('method')
    expect(sent.params).toEqual({ a: 1 })

    ws.onmessage!({ data: JSON.stringify({ jsonrpc: '2.0', result: 'ok', id: sent.id }) })
    await expect(p).resolves.toBe('ok')
  })

  it('rpc rejects on error response', async () => {
    const { connect, rpc } = useMklinkWs()
    connect(undefined, 'ws://localhost')
    ws.onopen!()

    const p = rpc('fail')
    const sent = JSON.parse(ws.sent[0])
    ws.onmessage!({ data: JSON.stringify({ jsonrpc: '2.0', error: { message: 'boom' }, id: sent.id }) })
    await expect(p).rejects.toThrow('boom')
  })

  it('rpc rejects when not connected', () => {
    const { rpc } = useMklinkWs()
    expect(rpc('x')).rejects.toThrow('WebSocket not connected')
  })

  it('connect with token sends auth RPC', () => {
    const { connect } = useMklinkWs()
    connect('my-token', 'ws://localhost')
    ws.onopen!()
    const sent = JSON.parse(ws.sent[0])
    expect(sent.method).toBe('auth')
    expect(sent.params).toEqual({ token: 'my-token' })
  })

  it('onclose rejects all pending', async () => {
    const { connect, rpc } = useMklinkWs()
    connect(undefined, 'ws://localhost')
    ws.onopen!()
    const p1 = rpc('a')
    const p2 = rpc('b')
    ws.onclose!()
    await expect(p1).rejects.toThrow('WebSocket closed')
    await expect(p2).rejects.toThrow('WebSocket closed')
  })
})
