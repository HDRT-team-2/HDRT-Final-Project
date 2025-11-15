<script setup lang="ts">
import { useTargetCommand } from '@/composables/useTargetCommand'

const { sendTarget, isSending, error } = useTargetCommand()

async function handleSend() {
  await sendTarget()
}
</script>

<template>
  <button
    @click="handleSend"
    :disabled="isSending"
    class="px-3 py-1 rounded bg-blue-500 text-white text-xs font-semibold hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition"
  >
    {{ isSending ? '전송 중...' : '확인' }}
  </button>
  <div v-if="error" class="text-xs text-red-500 mt-1">{{ error }}</div>
</template>