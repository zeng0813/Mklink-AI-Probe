<template>
  <WaveformViewer mode="SuperWatch" :device-connected="deviceConnected" />
</template>

<script setup lang="ts">
import WaveformViewer from './WaveformViewer.vue'

defineProps<{ deviceConnected: boolean }>()
</script>
