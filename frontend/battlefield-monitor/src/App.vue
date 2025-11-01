<script setup lang="ts">
import { useDetectionWebSocket } from '@/composables/useDetectionWebSocket'

// 앱 시작 시 자동 연결
useDetectionWebSocket()
</script>

<template>
  <router-view />
</template>

<style scoped></style>
