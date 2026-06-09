<template>
  <WaveformViewer mode="VOFA" :device-connected="deviceConnected" />
</template>

<script setup lang="ts">
import WaveformViewer from './WaveformViewer.vue'

defineProps<{ deviceConnected: boolean }>()
</script>
