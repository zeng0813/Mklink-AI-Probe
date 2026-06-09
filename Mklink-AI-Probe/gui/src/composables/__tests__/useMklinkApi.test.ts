import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// Mock import.meta.env before importing the module
vi.stubGlobal('import.meta', { env: { VITE_MKLINK_API: '' } })

import { useMklinkApi } from '../useMklinkApi'

describe('useMklinkApi', () => {
  let mockFetch: ReturnType<typeof vi.fn>

  beforeEach(() => {
    mockFetch = vi.fn()
    vi.stubGlobal('fetch', mockFetch)
  })

  afterEach(() => vi.restoreAllMocks())

  function jsonOk(body: unknown, status = 200) {
    return Promise.resolve({
      ok: status >= 200 && status < 300,
      status,
      statusText: 'OK',
      json: () => Promise.resolve(body),
    } as Response)
  }

  function jsonError(status: number, body: unknown, statusText = 'Error') {
    return Promise.resolve({
      ok: false,
      status,
      statusText,
      json: () => Promise.resolve(body),
    } as Response)
  }

  it('parses string detail from error', async () => {
    mockFetch.mockReturnValue(jsonError(400, { detail: 'port not found' }))
    const api = useMklinkApi()
    await expect(api.listPorts()).rejects.toThrow('port not found')
  })

  it('joins array detail with semicolons', async () => {
    mockFetch.mockReturnValue(jsonError(422, {
      detail: [{ msg: 'field required' }, { msg: 'invalid type' }],
    }))
    const api = useMklinkApi()
    await expect(api.listPorts()).rejects.toThrow('field required; invalid type')
  })

  it('stringifies object detail', async () => {
    mockFetch.mockReturnValue(jsonError(400, { detail: { code: 400 } }))
    const api = useMklinkApi()
    await expect(api.listPorts()).rejects.toThrow('[object Object]')
  })

  it('falls back to statusText when body is not JSON', async () => {
    mockFetch.mockReturnValue(Promise.resolve({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
      json: () => Promise.reject(new Error('not json')),
    } as Response))
    const api = useMklinkApi()
    await expect(api.listPorts()).rejects.toThrow('Internal Server Error')
  })

  it('throws TypeError on network failure', async () => {
    mockFetch.mockRejectedValue(new TypeError('Failed to fetch'))
    const api = useMklinkApi()
    await expect(api.listPorts()).rejects.toThrow(TypeError)
  })

  it('listPorts returns parsed data', async () => {
    const ports = [{ device: 'COM3', description: 'MKLink' }]
    mockFetch.mockReturnValue(jsonOk(ports))
    const api = useMklinkApi()
    const result = await api.listPorts()
    expect(result).toEqual(ports)
  })

  it('getConfig returns parsed config', async () => {
    const config = { com_port: 'COM3', mcu_key: 'n32g435' }
    mockFetch.mockReturnValue(jsonOk(config))
    const api = useMklinkApi()
    const result = await api.getConfig()
    expect(result).toEqual(config)
  })

  it('startStatusPolling refreshes then intervals', () => {
    vi.useFakeTimers()
    mockFetch.mockReturnValue(jsonOk({
      connected: false, state: 'disconnected', mcu: null, idcode: null, port: null,
    }))
    const api = useMklinkApi()
    api.startStatusPolling(1000)
    expect(mockFetch).toHaveBeenCalledTimes(1)
    vi.advanceTimersByTime(3000)
    expect(mockFetch).toHaveBeenCalledTimes(4)
    api.stopStatusPolling()
    vi.advanceTimersByTime(3000)
    expect(mockFetch).toHaveBeenCalledTimes(4)
    vi.useRealTimers()
  })

  it('refreshStatus resets to disconnected on error', async () => {
    mockFetch.mockRejectedValue(new Error('network'))
    const api = useMklinkApi()
    const s = await api.refreshStatus()
    expect(s.connected).toBe(false)
    expect(s.state).toBe('disconnected')
  })

  it('getRttConfig returns parsed config including storage mode', async () => {
    const cfg = {
      rtt_addr: '0x2001F800',
      rtt_storage_mode: 1,
      channel: 0,
      search_size: 1024,
    }
    mockFetch.mockReturnValue(jsonOk(cfg))
    const api = useMklinkApi()
    const result = await api.getRttConfig()
    expect(result).toEqual(cfg)
    expect(result.rtt_storage_mode).toBe(1)
  })

  it('updateRttConfig passes rtt_storage_mode through to PUT /api/rtt-config', async () => {
    mockFetch.mockReturnValue(jsonOk({}))
    const api = useMklinkApi()
    await api.updateRttConfig({
      rtt_addr: '0x2001F800',
      rtt_storage_mode: 1,
      channel: 0,
    })
    expect(mockFetch).toHaveBeenCalledTimes(1)
    const [url, init] = mockFetch.mock.calls[0]
    expect(url).toContain('/api/rtt-config')
    expect(init.method).toBe('PUT')
    const body = JSON.parse(init.body)
    expect(body.rtt_storage_mode).toBe(1)
    expect(body.rtt_addr).toBe('0x2001F800')
  })
})
