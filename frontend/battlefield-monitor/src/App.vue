<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
import { useDetectionWebSocket } from '@/composables/useDetectionWebSocket'
import { usePositionWebSocket } from '@/composables/usePositionWebSocket'
import { useFireWebSocket } from '@/composables/useFireWebSocket'

// Backend WebSocket 연결
useDetectionWebSocket()
usePositionWebSocket()
useFireWebSocket()
</script>

<template>
  <router-view />
</template>

<style scoped></style>
