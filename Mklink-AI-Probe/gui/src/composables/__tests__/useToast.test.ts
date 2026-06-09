import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.useFakeTimers()

// Reset module-level state between tests
let toasts: any
let dismiss: (id: number) => void
let success: (msg: string, duration?: number) => void
let error: (msg: string, duration?: number) => void
let warn: (msg: string, duration?: number) => void
let info: (msg: string, duration?: number) => void

beforeEach(async () => {
  vi.resetModules()
  const mod = await import('../useToast')
  const api = mod.useToast()
  toasts = api.toasts
  dismiss = api.dismiss
  success = api.success
  error = api.error
  warn = api.warn
  info = api.info
})

describe('useToast', () => {
  it('success creates toast with type=success', () => {
    success('ok')
    expect(toasts.value).toHaveLength(1)
    expect(toasts.value[0].type).toBe('success')
    expect(toasts.value[0].message).toBe('ok')
  })

  it('error creates toast with default 6s duration', () => {
    error('fail')
    expect(toasts.value[0].duration).toBe(6000)
  })

  it('success defaults to 4s duration', () => {
    success('ok')
    expect(toasts.value[0].duration).toBe(4000)
  })

  it('auto-dismisses after duration', () => {
    success('gone')
    expect(toasts.value).toHaveLength(1)
    vi.advanceTimersByTime(4000)
    expect(toasts.value).toHaveLength(0)
  })

  it('multiple toasts coexist', () => {
    success('a')
    error('b')
    warn('c')
    expect(toasts.value).toHaveLength(3)
  })

  it('dismiss removes specific toast', () => {
    success('keep')
    error('remove')
    dismiss(toasts.value[1].id)
    expect(toasts.value).toHaveLength(1)
    expect(toasts.value[0].message).toBe('keep')
  })

  it('custom duration overrides default', () => {
    success('slow', 10000)
    expect(toasts.value[0].duration).toBe(10000)
  })
})
