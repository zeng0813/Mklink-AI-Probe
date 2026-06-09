<template>
  <div class="symbols-tab">
    <div v-if="!deviceConnected" class="alert alert-warn">请先连接设备。</div>
    <template v-else>
      <div class="sym-controls">
        <input class="form-input" v-model="query" placeholder="搜索符号名..." @input="debouncedSearch" />
      </div>
      <div v-if="results.length > 0" class="sym-results">
        <div v-for="sym in results" :key="sym.name" class="sym-item" @click="selectSymbol(sym.name)">
          <span class="sym-name">{{ sym.name }}</span>
          <span class="sym-type">{{ sym.type }}</span>
          <span class="sym-addr">{{ formatAddr(sym.address) }}</span>
          <span class="sym-size">{{ sym.size }}B</span>
        </div>
      </div>
      <div v-else-if="query && !loading" class="sym-empty">无匹配符号</div>
      <div v-if="selectedType" class="sym-detail">
        <h4>类型信息: {{ selectedType.name }}</h4>
        <table class="desc-table" v-if="selectedType.found">
          <tr><th>类型</th><td>{{ selectedType.type }}</td></tr>
          <tr><th>大小</th><td>{{ selectedType.size }} bytes</td></tr>
          <tr><th>地址</th><td>{{ formatAddr(selectedType.address) }}</td></tr>
        </table>
        <div v-if="selectedType.members?.length" class="sym-members">
          <h5>成员</h5>
          <div v-for="(m, i) in selectedType.members" :key="i" class="sym-member">
            {{ JSON.stringify(m) }}
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useSymbolsApi } from '../../composables/useDashboard'
import { useToast } from '../../composables/useToast'
import type { SymbolEntry, SymbolTypeInfo } from '../../types/mklink'

defineProps<{ deviceConnected: boolean }>()

const symbols = useSymbolsApi()
const toast = useToast()
const query = ref('')
const loading = ref(false)
const results = ref<SymbolEntry[]>([])
const selectedType = ref<SymbolTypeInfo | null>(null)

let debounceTimer: ReturnType<typeof setTimeout> | null = null

function debouncedSearch() {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(doSearch, 300)
}

async function doSearch() {
  if (!query.value.trim()) { results.value = []; return }
  loading.value = true
  try {
    const res = await symbols.search(query.value)
    results.value = res.results || []
  } catch (e: unknown) {
    results.value = []
    if (e instanceof Error && !e.message.includes('No DWARF')) {
      toast.error(e.message)
    }
  } finally {
    loading.value = false
  }
}

async function selectSymbol(name: string) {
  try {
    selectedType.value = await symbols.typeinfo(name)
  } catch (e: unknown) {
    toast.error(e instanceof Error ? e.message : String(e))
  }
}

function formatAddr(addr: unknown): string {
  if (addr == null) return '—'
  if (typeof addr === 'number') return '0x' + addr.toString(16).toUpperCase().padStart(8, '0')
  return String(addr)
}
</script>

<style scoped>
.symbols-tab { display: flex; flex-direction: column; gap: 12px; }
.sym-controls { display: flex; gap: 8px; }
.sym-controls .form-input { flex: 1; }
.sym-results { max-height: 300px; overflow-y: auto; }
.sym-item {
  display: flex; gap: 12px; padding: 4px 8px; cursor: pointer;
  font-family: Consolas, monospace; font-size: 12px; border-radius: 3px;
}
.sym-item:hover { background: var(--surface); }
.sym-name { min-width: 120px; color: var(--fg); }
.sym-type { color: var(--info); min-width: 80px; }
.sym-addr { color: var(--info); min-width: 80px; }
.sym-size { color: var(--muted); }
.sym-empty { color: var(--muted); padding: 16px; text-align: center; }
.sym-detail { border-top: 1px solid var(--border); padding-top: 12px; }
.sym-detail h4 { margin: 0 0 8px; font-size: 13px; }
.sym-members { margin-top: 8px; }
.sym-members h5 { margin: 0 0 4px; font-size: 12px; }
.sym-member { font-family: Consolas, monospace; font-size: 11px; padding: 2px 0; color: var(--muted); }
.alert-warn { color: var(--warn); padding: 8px; border: 1px solid var(--warn); border-radius: 4px; }
</style>
