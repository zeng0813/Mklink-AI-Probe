<template>
  <div class="memory-tab">
    <div v-if="!deviceConnected" class="alert alert-warn">请先连接设备。</div>
    <template v-else>
      <div class="mem-controls">
        <input class="form-input addr-input" v-model="address" placeholder="0x20000000" />
        <input class="form-input size-input" v-model.number="size" type="number" placeholder="64" min="1" max="4096" />
        <button class="btn btn-primary" @click="doRead" :disabled="loading">读取</button>
      </div>
      <div v-if="result" class="mem-result">
        <HexMemoryView :data-hex="result.data_hex" :base-address="result.address" />
      </div>
      <div class="mem-write" v-if="result">
        <h4>写入内存</h4>
        <div class="mem-controls">
          <input class="form-input addr-input" v-model="writeAddr" placeholder="地址" />
          <input class="form-input" v-model="writeHex" placeholder="十六进制数据 (如: 0102A0FF)" />
          <button class="btn" @click="doWrite" :disabled="writing">写入</button>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useDeviceApi } from '../../composables/useDashboard'
import { useToast } from '../../composables/useToast'
import HexMemoryView from './HexMemoryView.vue'
import type { MemoryReadResult } from '../../types/mklink'

defineProps<{ deviceConnected: boolean }>()

const device = useDeviceApi()
const toast = useToast()
const address = ref('0x20000000')
const size = ref(64)
const writeAddr = ref('')
const writeHex = ref('')
const loading = ref(false)
const writing = ref(false)
const result = ref<MemoryReadResult | null>(null)

async function doRead() {
  loading.value = true
  try {
    result.value = await device.readMemory(address.value, size.value) as MemoryReadResult
    writeAddr.value = result.value.address
  } catch (e: unknown) {
    toast.error(e instanceof Error ? e.message : String(e))
  } finally {
    loading.value = false
  }
}

async function doWrite() {
  if (!writeHex.value.trim()) return
  writing.value = true
  try {
    await device.writeMemory(writeAddr.value, writeHex.value.replace(/\s/g, ''))
    toast.success('写入成功')
    await doRead()
  } catch (e: unknown) {
    toast.error(e instanceof Error ? e.message : String(e))
  } finally {
    writing.value = false
  }
}
</script>

<style scoped>
.memory-tab { display: flex; flex-direction: column; gap: 12px; }
.mem-controls { display: flex; gap: 8px; align-items: center; }
.addr-input { width: 140px; }
.size-input { width: 80px; }
.mem-result { margin-top: 4px; }
.mem-write { margin-top: 12px; border-top: 1px solid var(--border); padding-top: 12px; }
.mem-write h4 { margin: 0 0 8px; font-size: 13px; }
.alert-warn { color: var(--warn); padding: 8px; border: 1px solid var(--warn); border-radius: 4px; }
</style>
