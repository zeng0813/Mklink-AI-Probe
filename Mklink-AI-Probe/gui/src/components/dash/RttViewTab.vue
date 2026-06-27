<template>
  <div class="rtt-view-tab">
    <div v-if="!deviceConnected" class="alert alert-warn">请先连接设备。</div>
    <template v-else>
      <div class="rtt-view-toolbar">
        <ControlToolbar
          :state="dash.state.value"
          :error="dash.error.value"
          :device-connected="deviceConnected"
          @start="onStart"
          @pause="dash.pause()"
          @resume="dash.resume()"
          @stop="onStop"
        />
        <span v-if="logLines.length > 0" class="line-count">{{ logLines.length }} 行</span>
        <button v-if="logLines.length > 0" class="btn-clear" @click="clearLogs()">清除</button>
        <label v-if="dash.state.value === 'running'" class="auto-scroll-toggle">
          <input type="checkbox" v-model="autoScroll" />
          自动滚动
        </label>
      </div>
      <div
        class="rtt-view-log"
        ref="logBody"
        role="log"
        aria-live="polite"
        aria-relevant="additions text"
        aria-atomic="false"
        aria-label="RTT View log"
        tabindex="0"
        @scroll="onScroll"
      >
        <div v-for="line in logLines" :key="line.num" class="rtt-log-line">
          <span class="line-num">{{ line.num }}</span>
          <span class="timestamp">{{ line.ts }}</span>
          <span class="line-content" :class="line.type">{{ line.text }}</span>
        </div>
        <div v-if="streamEnded" class="stream-ended">[Stream ended]</div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { useDashboard } from '../../composables/useDashboard'
import { useEventSource } from '../../composables/useEventSource'
import { useResourceStatus } from '../../composables/useResourceStatus'
import { takeNewStreamPoints } from '../../lib/streamCursor'
import ControlToolbar from './ControlToolbar.vue'

interface LogLine {
  num: number
  ts: string
  text: string
  type: 'data' | 'raw' | 'stopped'
}

const props = defineProps<{ deviceConnected: boolean }>()

const dash = useDashboard('rtt')
const { data, connected: sseConnected, connect, disconnect } = useEventSource('/api/dash/rtt/stream')
const { checkConflict } = useResourceStatus()

const logLines = ref<LogLine[]>([])
const autoScroll = ref(true)
const streamEnded = ref(false)
const logBody = ref<HTMLElement | null>(null)
let lineCounter = 0
let lastStreamSeq = 0
const MAX_LINES = 5000
const SCROLL_FOLLOW_THRESHOLD = 24

const DASH_NAMES: Record<string, string> = {
  rtt: 'RTT', superwatch: 'SuperWatch', vofa: 'VOFA+',
}

function formatTimestamp(t: number | undefined): string {
  if (!t) return ''
  const d = new Date(t * 1000)
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  const ss = String(d.getSeconds()).padStart(2, '0')
  const ms = String(d.getMilliseconds()).padStart(3, '0')
  return `${hh}:${mm}:${ss}.${ms}`
}

function formatDataEvent(dp: Record<string, unknown>): string {
  return Object.entries(dp)
    .filter(([k]) => !k.startsWith('_'))
    .map(([k, v]) => {
      if (typeof v === 'number') return `${k}=${v.toFixed(3)}`
      return `${k}=${v}`
    })
    .join('  ')
}

function addLine(text: string, type: LogLine['type'], t?: number) {
  lineCounter++
  logLines.value.push({
    num: lineCounter,
    ts: formatTimestamp(t),
    text,
    type,
  })
  if (logLines.value.length > MAX_LINES) {
    logLines.value = logLines.value.slice(-MAX_LINES)
  }
}

function isNearBottom(el: HTMLElement): boolean {
  return el.scrollHeight - el.scrollTop - el.clientHeight <= SCROLL_FOLLOW_THRESHOLD
}

function scrollToBottom() {
  if (!logBody.value) return
  logBody.value.scrollTop = logBody.value.scrollHeight
}

function latestBufferedStreamSeq(): number {
  return (data.value as any[]).reduce((latest, point) => {
    const seq = point?._streamSeq
    return typeof seq === 'number' && seq > latest ? seq : latest
  }, lastStreamSeq)
}

// SSE data is bounded, so array length can stay constant while new points arrive.
// Use monotonic stream sequence numbers instead of length-based diffing.
watch(data, (newData) => {
  const fresh = takeNewStreamPoints(newData as any[], lastStreamSeq)
  for (const dp of fresh.points as any[]) {
    const evt = dp.event || dp._event
    const t = dp._t as number | undefined
    if (evt === 'raw') {
      addLine(dp.line as string, 'raw', t)
    } else if (evt === 'data' || !evt) {
      addLine(formatDataEvent(dp as Record<string, unknown>), 'data', t)
    }
  }
  lastStreamSeq = fresh.nextSeq
  if (autoScroll.value) {
    nextTick(scrollToBottom)
  }
})

watch(autoScroll, (enabled) => {
  if (enabled) nextTick(scrollToBottom)
})

watch(sseConnected, (now, was) => {
  if (was && !now && dash.state.value === 'running') {
    streamEnded.value = true
    addLine('[Stream ended]', 'stopped')
  }
})

function onScroll() {
  if (!logBody.value) return
  autoScroll.value = isNearBottom(logBody.value)
}

function clearLogs(options: { resetCursor?: boolean } = {}) {
  logLines.value = []
  lineCounter = 0
  lastStreamSeq = options.resetCursor ? 0 : latestBufferedStreamSeq()
  streamEnded.value = false
  autoScroll.value = true
}

async function onStart() {
  const conflicts = await checkConflict('rtt')
  if (conflicts.length > 0) {
    const names = conflicts.map(c => DASH_NAMES[c] || c).join('、')
    if (!confirm(`启动 RTT 将停止当前运行的 ${names} 会话。确认？`)) return
  }
  clearLogs({ resetCursor: true })
  await dash.start()
  setTimeout(() => {
    connect()
  }, 500)
}

async function onStop() {
  disconnect()
  await dash.stop()
}
</script>

<style scoped>
.rtt-view-tab {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  min-width: 0;
  overflow: hidden;
}
.alert-warn { color: var(--warn); padding: 8px; border: 1px solid var(--warn); border-radius: 4px; }
.rtt-view-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  flex: 0 0 auto;
  flex-wrap: wrap;
  min-width: 0;
}
.line-count {
  color: var(--muted);
  font-size: 12px;
}
.btn-clear {
  background: none;
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--muted);
  cursor: pointer;
  font-size: 12px;
  padding: 2px 8px;
}
.btn-clear:hover {
  color: var(--fg);
  border-color: var(--fg);
}
.auto-scroll-toggle {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--muted);
  cursor: pointer;
  margin-left: auto;
  user-select: none;
}
.rtt-view-log {
  flex: 1 1 auto;
  min-height: 160px;
  min-width: 0;
  width: 100%;
  margin-top: 8px;
  background: #1e1e1e;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 8px;
  overflow: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.6;
  color: #ccc;
}
.rtt-view-log:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.rtt-log-line {
  display: flex;
  gap: 10px;
  align-items: baseline;
  width: max-content;
  min-width: 100%;
  white-space: pre;
}
.line-num {
  flex: 0 0 50px;
  text-align: right;
  color: var(--dim);
  user-select: none;
}
.timestamp {
  flex: 0 0 92px;
  color: var(--dim);
  user-select: none;
}
.line-content {
  flex: 0 0 auto;
  white-space: pre;
}
.line-content.data {
  color: #8be9fd;
}
.line-content.raw {
  color: #ccc;
}
.line-content.stopped {
  color: var(--dim);
  font-style: italic;
}
.stream-ended {
  color: var(--dim);
  font-style: italic;
  padding: 4px 0;
}
</style>
