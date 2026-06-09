<template>
  <div>
    <div v-if="!deviceConnected" class="alert alert-warn">请先连接设备。</div>
    <template v-else>
      <!-- Config + controls -->
      <div class="form-row" style="gap:8px;flex-wrap:wrap;align-items:end">
        <div>
          <label class="form-label" style="font-size:12px">端口</label>
          <select v-model="portName" class="form-input" style="width:120px">
            <option v-for="p in ports" :key="p.device" :value="p.device">{{ p.device }}</option>
          </select>
        </div>
        <div>
          <label class="form-label" style="font-size:12px">波特率</label>
          <select v-model="baudrate" class="form-input" style="width:100px">
            <option v-for="b in [9600,19200,38400,57600,115200,230400,460800,921600]" :key="b" :value="b">{{ b }}</option>
          </select>
        </div>
        <div>
          <label class="form-label" style="font-size:12px">数据位</label>
          <select v-model="databits" class="form-input" style="width:60px">
            <option :value="8">8</option>
            <option :value="7">7</option>
          </select>
        </div>
        <div>
          <label class="form-label" style="font-size:12px">停止位</label>
          <select v-model="stopbits" class="form-input" style="width:60px">
            <option :value="1">1</option>
            <option :value="2">2</option>
          </select>
        </div>
        <div>
          <label class="form-label" style="font-size:12px">校验</label>
          <select v-model="parity" class="form-input" style="width:60px">
            <option value="N">无</option>
            <option value="E">偶</option>
            <option value="O">奇</option>
          </select>
        </div>
        <button v-if="!running" class="btn btn-primary" @click="doStart">开始监控</button>
        <button v-else class="btn btn-danger" @click="doStop">停止</button>
      </div>

      <!-- Send panel -->
      <div v-if="running" class="form-row" style="gap:8px;margin-top:8px">
        <input
          v-model="sendText"
          class="form-input" style="flex:1"
          placeholder="输入要发送的数据..."
          @keydown.enter="doSend"
        />
        <label style="font-size:12px;display:flex;align-items:center;gap:4px">
          <input type="checkbox" v-model="sendHex" /> HEX
        </label>
        <button class="btn" @click="doSend" :disabled="!sendText.trim()">发送</button>
        <button class="btn" @click="doClear">清空</button>
      </div>

      <!-- Stats -->
      <div v-if="running" style="margin-top:8px;font-size:12px;color:#888;display:flex;gap:16px">
        <span>RX: {{ stats.rx_count }} ({{ stats.rx_bytes }}B)</span>
        <span>TX: {{ stats.tx_count }} ({{ stats.tx_bytes }}B)</span>
        <span>速率: {{ stats.bytes_per_sec }} B/s</span>
        <span>端口: {{ currentPortStatus }}</span>
      </div>

      <!-- Event log -->
      <div v-if="running || events.length" class="serial-log" ref="logEl">
        <div v-for="(evt, i) in events" :key="i" class="serial-line" :class="evt.direction === 'TX' ? 'tx' : 'rx'">
          <span class="ts">{{ evt.timestamp }}</span>
          <span class="dir" :class="evt.direction">{{ evt.direction }}</span>
          <span class="hex">{{ evt.raw_hex }}</span>
          <span v-if="evt.ascii && evt.ascii.trim()" class="ascii">{{ evt.ascii.trim() }}</span>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { useMklinkApi } from '../../composables/useMklinkApi'
import { useToast } from '../../composables/useToast'
import type { SerialEvent, PortInfo } from '../../types/mklink'

const API_BASE = import.meta.env.VITE_MKLINK_API || ''

const props = defineProps<{ deviceConnected: boolean }>()
const toast = useToast()
const { listPorts: fetchPorts } = useMklinkApi()

const ports = ref<PortInfo[]>([])
const portName = ref('')
const baudrate = ref(115200)
const databits = ref(8)
const stopbits = ref(1)
const parity = ref('N')
const running = ref(false)
const sendText = ref('')
const sendHex = ref(false)
const events = ref<SerialEvent[]>([])
const stats = ref({ rx_count: 0, tx_count: 0, rx_bytes: 0, tx_bytes: 0, bytes_per_sec: 0 })
const currentPortStatus = ref('closed')
const logEl = ref<HTMLElement | null>(null)

let es: EventSource | null = null
const maxEvents = 2000

onMounted(async () => {
  try {
    ports.value = await fetchPorts()
    if (ports.value.length) portName.value = ports.value[0].device
  } catch { /* ignore */ }
})

onUnmounted(() => {
  doStop()
})

async function doStart() {
  if (!portName.value) { toast.error('请选择端口'); return }
  try {
    await fetch(`${API_BASE}/api/dash/serial/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ports: [{ port: portName.value, baudrate: baudrate.value,
                   databits: databits.value, stopbits: stopbits.value, parity: parity.value }],
      }),
    })
    running.value = true
    events.value = []
    connectSSE()
    toast.success('串口监控已启动')
  } catch (e: any) {
    toast.error('启动失败: ' + e.message)
  }
}

function doStop() {
  if (es) { es.close(); es = null }
  if (!running.value) return
  running.value = false
  fetch(`${API_BASE}/api/dash/serial/stop`, { method: 'POST' }).catch(() => {})
  toast.info('串口监控已停止')
}

function connectSSE() {
  if (es) { es.close(); es = null }
  es = new EventSource(`${API_BASE}/api/dash/serial/stream`)
  es.onmessage = (e) => {
    try {
      const d = JSON.parse(e.data)
      if (d.event === 'data') {
        events.value.push(d)
        if (events.value.length > maxEvents) events.value = events.value.slice(-maxEvents)
        nextTick(() => { if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight })
      } else if (d.event === 'status') {
        const portStatuses = d.ports || {}
        currentPortStatus.value = Object.values(portStatuses).join(', ') || 'open'
        if (d.stats) stats.value = d.stats
      } else if (d.event === 'stopped') {
        running.value = false
        if (es) { es.close(); es = null }
      }
    } catch { /* ignore */ }
  }
  es.onerror = () => {
    if (es?.readyState === EventSource.CLOSED) running.value = false
  }
}

async function doSend() {
  if (!sendText.value.trim()) return
  try {
    await fetch(`${API_BASE}/api/dash/serial/send`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ port: portName.value, data: sendText.value, hex: sendHex.value }),
    })
    sendText.value = ''
  } catch (e: any) {
    toast.error('发送失败: ' + e.message)
  }
}

function doClear() {
  events.value = []
}
</script>

<style scoped>
.serial-log {
  margin-top: 8px;
  background: #1e1e1e;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 8px;
  max-height: 400px;
  overflow-y: auto;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.6;
}
.serial-line {
  display: flex;
  gap: 8px;
  align-items: baseline;
}
.serial-line.rx { color: var(--success); }
.serial-line.tx { color: var(--warn); }
.ts { color: var(--dim); min-width: 90px; }
.dir { font-weight: bold; min-width: 24px; }
.dir.RX { color: var(--success); }
.dir.TX { color: var(--warn); }
.hex { color: var(--info); word-break: break-all; }
.ascii { color: var(--muted); margin-left: 8px; }
.alert-warn { color: var(--warn); padding: 8px; border: 1px solid var(--warn); border-radius: 4px; }
</style>
