<template>
  <div class="variable-chips" v-if="channels.length > 0">
    <button
      v-for="ch in channels"
      :key="ch"
      class="chip"
      :class="{ active: activeSet.has(ch) }"
      :style="activeSet.has(ch) ? { borderColor: colorFor(ch), color: colorFor(ch) } : {}"
      @click="$emit('toggle', ch)"
    >
      {{ ch }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  channels: string[]
  activeChannels: Set<string>
}>()

defineEmits<{ toggle: [name: string] }>()

const activeSet = computed(() => props.activeChannels)

const COLORS = [
  '#4a9eff', '#ff6b6b', '#51cf66', '#ffd43b',
  '#cc5de8', '#ff922b', '#20c997', '#f06595',
]

function colorFor(name: string): string {
  let hash = 0
  for (let i = 0; i < name.length; i++) {
    hash = ((hash << 5) - hash) + name.charCodeAt(i)
  }
  return COLORS[Math.abs(hash) % COLORS.length]
}
</script>

<style scoped>
.variable-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 4px 0;
}
.chip {
  padding: 2px 10px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  font-size: 12px;
  transition: all 0.15s;
}
.chip:hover { background: var(--surface); }
.chip.active { background: rgba(201, 100, 66, 0.08); }
</style>
