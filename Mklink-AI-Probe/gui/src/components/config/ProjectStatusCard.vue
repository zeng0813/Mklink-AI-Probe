<template>
  <div class="card">
    <div class="card-title">项目状态</div>
    <div v-if="hasData" class="status-grid">
      <div class="status-field">
        <span class="field-label">HEX</span>
        <span class="field-value mono">{{ projectInfo?.hex_path || '—' }}</span>
      </div>
      <div class="status-field">
        <span class="field-label">MAP</span>
        <span class="field-value mono">{{ projectInfo?.map_path || '—' }}</span>
      </div>
      <div class="status-field">
        <span class="field-label">FLM</span>
        <span class="field-value">{{ projectInfo?.flm_name || '—' }}</span>
      </div>
      <div class="status-field">
        <span class="field-label">Flash 基址</span>
        <span class="field-value mono">{{ projectInfo?.flash_base || '—' }}</span>
      </div>
      <div class="status-field">
        <span class="field-label">MICROKEEN</span>
        <span v-if="microkeen?.available" class="badge badge-ok">可用 {{ microkeen.disk_path }}</span>
        <span v-else class="badge badge-err">未找到</span>
      </div>
      <div class="status-field">
        <span class="field-label">配置</span>
        <span v-if="configStatus?.is_valid && !configStatus?.warnings?.length" class="badge badge-ok">正常</span>
        <span v-else-if="configStatus?.errors?.length" class="badge badge-err">{{ configStatus.errors.length }} 错误</span>
        <span v-else-if="configStatus?.warnings?.length" class="badge badge-warn">{{ configStatus.warnings.length }} 警告</span>
        <span v-else class="badge">未加载</span>
      </div>
    </div>
    <div v-else class="empty-hint">暂无工程信息，请先设置项目目录并运行初始化。</div>
    <div v-if="configStatus?.errors?.length" class="alert alert-error" style="margin-top:8px">
      <ul><li v-for="e in configStatus.errors" :key="e">{{ e }}</li></ul>
    </div>
    <div v-if="configStatus?.warnings?.length" class="alert alert-warn" style="margin-top:4px">
      <ul><li v-for="w in configStatus.warnings" :key="w">{{ w }}</li></ul>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ProjectInfo, ConfigStatus, MicrokeenInfo } from '../../types/mklink'

const props = defineProps<{
  projectInfo: ProjectInfo | null
  configStatus: ConfigStatus | null
  microkeen: MicrokeenInfo | null
}>()

const hasData = computed(() => {
  return (props.projectInfo && Object.keys(props.projectInfo).length > 0) || props.microkeen?.available
})
</script>

<style scoped>
.status-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px 16px;
}
.status-field {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  min-height: 22px;
}
.field-label {
  color: var(--dim);
  min-width: 60px;
  flex-shrink: 0;
}
.field-value {
  color: var(--fg);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mono {
  font-family: var(--font-mono);
  font-size: 11px;
}
.empty-hint {
  color: var(--dim);
  font-size: 13px;
  padding: 8px 0;
}
.alert ul { margin: 4px 0 0 16px; padding: 0; }
.alert li { margin: 2px 0; font-size: 12px; }
.badge-warn {
  background: #f5f0e1;
  color: var(--warn);
}
</style>
