<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
import { useDetectionWebSocket } from '@/composables/useDetectionWebSocket'
import { usePositionWebSocket } from '@/composables/usePositionWebSocket'
import { useFireWebSocket } from '@/composables/useFireWebSocket'
import { useMissionWebSocket } from '@/composables/useMissionWebSocket'

// Backend WebSocket 연결
useDetectionWebSocket()
usePositionWebSocket()
useFireWebSocket()
useMissionWebSocket()
</script>

<template>
  <router-view />
</template>

<style scoped></style>
