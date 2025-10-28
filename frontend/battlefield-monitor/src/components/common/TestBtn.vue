<script setup lang="ts">
import { ref } from 'vue'
import { storeToRefs } from 'pinia'
import { usePositionStore } from '@/stores/position'
import { useMockPositionWebSocket } from '@/composables/usePositionWebSocket'
import { useMockTargetCommand } from '@/composables/useTargetCommand'
import { useMockDetectionWebSocket } from '@/composables/useDetectionWebSocket'

const positionStore = usePositionStore()
const { hasTarget, target } = storeToRefs(positionStore)

// Mock Position WebSocket
const mockPositionWs = useMockPositionWebSocket()
const isMoving = ref(false)

// Mock Detection WebSocket
const mockDetectionWs = useMockDetectionWebSocket()
const isDetecting = ref(false)

// Detection Store
import { useDetectionStore } from '@/stores/detection'
const detectionStore = useDetectionStore()

// Mock Target Command
const { isSending, error, sendTarget } = useMockTargetCommand(mockPositionWs)

/**
 * 테스트 실행 버튼
 * 1. Position WebSocket 시작 (전차 이동)
 * 2. Detection WebSocket 시작 (객체 탐지)
 * 3. 타겟 전송 (API 호출)
 */
async function handleTestExecute() {
  // 1. Position WebSocket 시작
  const success = await sendTarget()
  
  if (success) {
    isMoving.value = true
    console.log('✅ Position 테스트 실행')
  } else {
    console.error('❌ 실행 실패:', error.value)
  }
  
  // 2. Detection WebSocket 시작
  mockDetectionWs.start()
  isDetecting.value = true
  console.log('✅ Detection 테스트 실행')
}

/**
 * 테스트 정지
 */
function handleTestStop() {
  // Position WebSocket 중지
  mockPositionWs.stop()
  isMoving.value = false
  
  // Detection WebSocket 중지
  mockDetectionWs.stop()
  isDetecting.value = false
  
  // 탐지 객체 초기화
  detectionStore.clearObjects()
  
  console.log('🛑 테스트 정지')
}
</script>

<template>
  <div class="p-3 bg-gray-100 border-2 border-dashed border-red-400 rounded-lg">
    <h3 class="text-sm font-bold text-red-500 mb-2">🧪 테스트 컨트롤</h3>
    
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
      <p>객체 탐지: {{ isDetecting ? '🟢 진행 중' : '🔴 정지' }}</p>
      <p>목표 설정: {{ hasTarget ? `🎯 (${target?.x}, ${target?.y})` : '❌ 미설정' }}</p>
      <p v-if="error" class="text-red-500 font-bold">{{ error }}</p>
    </div>
  </div>
</template>