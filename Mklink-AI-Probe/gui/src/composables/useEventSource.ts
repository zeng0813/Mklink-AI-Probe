import { ref, readonly, onUnmounted } from 'vue'
import type { DataPoint } from '../types/mklink'

const API_BASE = import.meta.env.VITE_MKLINK_API || ''

export function useEventSource(url: string) {
  const data = ref<DataPoint[]>([])
  const connected = ref(false)
  const error = ref<string | null>(null)

  let es: EventSource | null = null
  const maxPoints = 500

  function connect() {
    disconnect()
    data.value = []
    error.value = null

    es = new EventSource(`${API_BASE}${url}`)

    es.onopen = () => {
      connected.value = true
      error.value = null
    }

    es.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data)
        if (parsed.event === 'data') {
          data.value.push(parsed)
          if (data.value.length > maxPoints) {
            data.value = data.value.slice(-maxPoints)
          }
        } else if (parsed.event === 'raw') {
          data.value.push(parsed)
          if (data.value.length > maxPoints) {
            data.value = data.value.slice(-maxPoints)
          }
        } else if (parsed.event === 'history') {
          // Initial history replay
          const points = parsed.points || []
          data.value = points.slice(-maxPoints)
        } else if (parsed.event === 'error') {
          error.value = parsed.message
        } else if (parsed.event === 'stopped') {
          connected.value = false
        }
      } catch {
        // ignore parse errors
      }
    }

    es.onerror = () => {
      connected.value = false
      if (es?.readyState === EventSource.CLOSED) {
        error.value = 'Connection closed'
      }
    }
  }

  function disconnect() {
    if (es) {
      es.close()
      es = null
    }
    connected.value = false
  }

  onUnmounted(() => {
    disconnect()
  })

  return {
    data: readonly(data),
    connected: readonly(connected),
    error: readonly(error),
    connect,
    disconnect,
  }
}
