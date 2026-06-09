<template>
  <div class="hex-view">
    <div class="hex-header">
      <span class="hex-addr-hdr">Address</span>
      <span v-for="i in 16" :key="i" class="hex-byte-hdr">{{ (i - 1).toString(16).toUpperCase().padStart(2, '0') }}</span>
      <span class="hex-ascii-hdr">ASCII</span>
    </div>
    <div class="hex-body">
      <div v-for="(row, ri) in rows" :key="ri" class="hex-row">
        <span class="hex-addr">{{ row.addr }}</span>
        <span v-for="(byte, bi) in row.bytes" :key="bi" class="hex-byte" :class="{ zero: byte.value === 0 }">{{ byte.hex }}</span>
        <span class="hex-ascii">{{ row.ascii }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  dataHex: string
  baseAddress?: string | number
}>()

interface ByteInfo { hex: string; value: number }
interface RowInfo { addr: string; bytes: ByteInfo[]; ascii: string }

const rows = computed(() => {
  const hex = props.dataHex || ''
  const bytes: ByteInfo[] = []
  for (let i = 0; i < hex.length; i += 2) {
    const h = hex.slice(i, i + 2)
    bytes.push({ hex: h.toUpperCase(), value: parseInt(h, 16) })
  }
  const base = typeof props.baseAddress === 'string'
    ? parseInt(props.baseAddress)
    : (props.baseAddress || 0)

  const result: RowInfo[] = []
  for (let i = 0; i < bytes.length; i += 16) {
    const chunk = bytes.slice(i, i + 16)
    const addr = (base + i).toString(16).toUpperCase().padStart(8, '0')
    const ascii = chunk.map(b => (b.value >= 32 && b.value < 127) ? String.fromCharCode(b.value) : '.').join('')
    result.push({ addr, bytes: chunk, ascii })
  }
  return result
})
</script>

<style scoped>
.hex-view {
  font-family: 'Cascadia Code', 'Consolas', monospace;
  font-size: 11px;
  line-height: 1.5;
  overflow-x: auto;
}
.hex-header, .hex-row {
  display: flex;
  gap: 0;
  white-space: nowrap;
}
.hex-header {
  color: var(--muted);
  border-bottom: 1px solid var(--border);
  padding-bottom: 2px;
  margin-bottom: 2px;
}
.hex-addr, .hex-addr-hdr { width: 80px; min-width: 80px; color: var(--info); }
.hex-byte, .hex-byte-hdr { width: 22px; min-width: 22px; text-align: center; }
.hex-byte.zero { color: var(--dim); }
.hex-ascii, .hex-ascii-hdr { margin-left: 8px; color: var(--muted); }
.hex-ascii-hdr { width: 50px; }
</style>
