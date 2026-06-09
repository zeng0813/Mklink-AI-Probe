<template>
  <div>
    <div v-if="!deviceConnected" class="alert alert-warn">请先连接设备。</div>
    <template v-else>
      <!-- Config -->
      <div class="form-row" style="gap:8px;flex-wrap:wrap;align-items:end">
        <div>
          <label class="form-label" style="font-size:12px">端口</label>
          <select v-model="portName" class="form-input" style="width:120px">
            <option v-for="p in ports" :key="p.device" :value="p.device">{{ p.device }}</option>
          </select>
        </div>
        <div>
          <label class="form-label" style="font-size:12px">从站地址</label>
          <input type="number" v-model.number="slave" class="form-input" style="width:70px" min="1" max="247" />
        </div>
        <div>
          <label class="form-label" style="font-size:12px">波特率</label>
          <select v-model="baudrate" class="form-input" style="width:90px">
            <option v-for="b in [9600,19200,38400,57600,115200]" :key="b" :value="b">{{ b }}</option>
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
        <div>
          <label class="form-label" style="font-size:12px">轮询(ms)</label>
          <input type="number" v-model.number="interval" class="form-input" style="width:80px" min="100" step="100" />
        </div>
        <button v-if="!running" class="btn btn-primary" @click="doStart">连接</button>
        <button v-else class="btn btn-danger" @click="doStop">断开</button>
      </div>

      <!-- Register range config -->
      <div class="form-row" style="gap:8px;margin-top:8px;align-items:end">
        <div>
          <label class="form-label" style="font-size:12px">起始地址</label>
          <input type="number" v-model.number="regStart" class="form-input" style="width:80px" min="0" />
        </div>
        <div>
          <label class="form-label" style="font-size:12px">数量</label>
          <input type="number" v-model.number="regCount" class="form-input" style="width:70px" min="1" max="125" />
        </div>
      </div>

      <!-- Register grid -->
      <div v-if="running && registers.length" class="reg-grid" style="margin-top:10px">
        <div class="reg-header">
          <span>地址</span><span>HEX</span><span>DEC</span><span>操作</span>
        </div>
        <div v-for="reg in registers" :key="reg.addr" class="reg-row">
          <span class="reg-addr">{{ reg.addr }}</span>
          <span class="reg-hex">0x{{ (reg.value ?? 0).toString(16).toUpperCase().padStart(4, '0') }}</span>
          <span class="reg-dec">{{ reg.value ?? '—' }}</span>
          <button class="btn btn-sm" @click="openWrite(reg)">写</button>
        </div>
      </div>
      <div v-else-if="running" style="margin-top:10px;color:#888;font-size:13px">
        等待数据...
      </div>

      <!-- Write dialog -->
      <div v-if="writeTarget" class="modal-overlay" @click.self="writeTarget = null">
        <div class="modal-card">
          <div class="card-title">写入寄存器 {{ writeTarget.addr }}</div>
          <div class="form-row" style="gap:8px">
            <input v-model="writeValue" class="form-input" style="flex:1" placeholder="值 (十进制或 0xHEX)" />
            <button class="btn btn-primary" @click="doWrite">写入</button>
            <button class="btn" @click="writeTarget = null">取消</button>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useMklinkApi } from '../../composables/useMklinkApi'
import { useToast } from '../../composables/useToast'
import type { PortInfo } from '../../types/mklink'

const API_BASE = import.meta.env.VITE_MKLINK_API || ''

const props = defineProps<{ deviceConnected: boolean }>()
const toast = useToast()
const { listPorts: fetchPorts } = useMklinkApi()

const ports = ref<PortInfo[]>([])
const portName = ref('')
const slave = ref(1)
const baudrate = ref(9600)
const parity = ref('N')
const interval = ref(1000)
const regStart = ref(0)
const regCount = ref(10)
const running = ref(false)
const registers = ref<{ addr: number; value: number | null }[]>([])
const writeTarget = ref<{ addr: number } | null>(null)
const writeValue = ref('')

let es: EventSource | null = null

onMounted(async () => {
  try {
    ports.value = await fetchPorts()
    if (ports.value.length) portName.value = ports.value[0].device
  } catch { /* ignore */ }
})

onUnmounted(() => {
  doStop()
})

function buildRegGrid() {
  const grid = []
  for (let i = 0; i < regCount.value; i++) {
    grid.push({ addr: regStart.value + i, value: null })
  }
  return grid
}

async function doStart() {
  if (!portName.value) { toast.error('请选择端口'); return }
  try {
    // Build register specs
    const regSpecs = []
    for (let i = 0; i < regCount.value; i++) {
      regSpecs.push({ addr: regStart.value + i, type: 'uint16', name: `R${regStart.value + i}` })
    }
    await fetch(`${API_BASE}/api/dash/modbus/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        port: portName.value,
        slave: slave.value,
        baudrate: baudrate.value,
        parity: parity.value,
        registers: regSpecs,
        interval: interval.value / 1000,
      }),
    })
    running.value = true
    registers.value = buildRegGrid()
    connectSSE()
    toast.success('Modbus 已连接')
  } catch (e: any) {
    toast.error('连接失败: ' + e.message)
  }
}

function doStop() {
  if (es) { es.close(); es = null }
  if (!running.value) return
  running.value = false
  fetch(`${API_BASE}/api/dash/modbus/stop`, { method: 'POST' }).catch(() => {})
  toast.info('Modbus 已断开')
}

function connectSSE() {
  if (es) { es.close(); es = null }
  es = new EventSource(`${API_BASE}/api/dash/modbus/stream`)
  es.onmessage = (e) => {
    try {
      const d = JSON.parse(e.data)
      if (d.event === 'data' && d.registers) {
        for (const reg of registers.value) {
          const entry = d.registers[reg.addr]
          if (entry) reg.value = entry.value
        }
      } else if (d.event === 'error') {
        toast.error(d.message)
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

function openWrite(reg: { addr: number }) {
  writeTarget.value = reg
  writeValue.value = ''
}

async function doWrite() {
  if (!writeTarget.value) return
  let val: number
  const v = writeValue.value.trim()
  if (v.startsWith('0x') || v.startsWith('0X')) {
    val = parseInt(v, 16)
  } else {
    val = parseInt(v, 10)
  }
  if (isNaN(val)) { toast.error('无效的数值'); return }
  try {
    await fetch(`${API_BASE}/api/dash/modbus/write`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ addr: writeTarget.value.addr, value: val }),
    })
    toast.success(`已写入寄存器 ${writeTarget.value.addr} = ${val}`)
    writeTarget.value = null
  } catch (e: any) {
    toast.error('写入失败: ' + e.message)
  }
}
</script>

<style scoped>
.reg-grid {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  font-size: 13px;
}
.reg-header, .reg-row {
  display: grid;
  grid-template-columns: 60px 80px 80px 60px;
  padding: 4px 8px;
}
.reg-header {
  background: var(--bg);
  color: var(--muted);
  font-weight: 600;
  border-bottom: 1px solid var(--border);
}
.reg-row {
  border-bottom: 1px solid var(--border-subtle);
}
.reg-row:hover { background: var(--bg); }
.reg-addr { color: var(--dim); }
.reg-hex { color: var(--info); font-family: var(--font-mono); }
.reg-dec { color: var(--fg); }
.btn-sm {
  font-size: 11px;
  padding: 2px 8px;
}
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.3);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}
.modal-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
  min-width: 320px;
}
.alert-warn { color: var(--warn); padding: 8px; border: 1px solid var(--warn); border-radius: 4px; }
</style>
