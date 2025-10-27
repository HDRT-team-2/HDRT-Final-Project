<script setup lang="ts">
import { ref } from 'vue'
import { storeToRefs } from 'pinia'
import { usePositionStore } from '@/stores/position'
import { useMockPositionWebSocket } from '@/composables/usePositionWebSocket'
import { useMockTargetCommand } from '@/composables/useTargetCommand'

const positionStore = usePositionStore()
const { hasTarget, target } = storeToRefs(positionStore)

// Mock WebSocket
const mockWs = useMockPositionWebSocket()

// Mock Target Command - mockWs를 전달!
const { isSending, error, sendTarget } = useMockTargetCommand(mockWs)

const isMoving = ref(false)

async function handleTestExecute() {
  const success = await sendTarget()
  
  if (success) {
    isMoving.value = true
    console.log('✅ 테스트 실행 완료')
  } else {
    console.error('❌ 실행 실패:', error.value)
  }
}

function handleTestStop() {
  mockWs.stop()
  isMoving.value = false
}
</script>

<template>
  <div class="p-3 bg-gray-100 border-2 border-dashed border-red-400 rounded-lg flex">
    
    <!-- 버튼 -->
    <div class="flex gap-2 mb-2">
      <button 
        @click="handleTestExecute"
        :disabled="isMoving || isSending"
        class="px-3 py-1 text-sm font-semibold text-white bg-green-500 rounded hover:bg-green-600 disabled:opacity-50 disabled:cursor-not-allowed transition"
      >
        {{ isSending ? '전송 중...' : '테스트 실행' }}
      </button>
      
      <button 
        @click="handleTestStop"
        :disabled="!isMoving"
        class="px-3 py-1 text-sm font-semibold text-white bg-red-500 rounded hover:bg-red-600 disabled:opacity-50 disabled:cursor-not-allowed transition"
      >
        정지
      </button>
    </div>
    
    <!-- 상태 표시 -->
    <div class="text-xs space-y-1">
      <p>전차 이동: {{ isMoving ? '🟢 진행 중' : '🔴 정지' }}</p>
      <p>목표 설정: {{ hasTarget ? `🎯 (${target?.x}, ${target?.y})` : '❌ 미설정' }}</p>
      <p v-if="error" class="text-red-500 font-bold">{{ error }}</p>
    </div>
  </div>
</template>