<script setup lang="ts">
import { ref } from 'vue'
import { storeToRefs } from 'pinia'
import { usePositionStore } from '@/stores/position'
import { useMockPositionWebSocket } from '@/composables/usePositionWebSocket'
import { useMockTargetCommand } from '@/composables/useTargetCommand'
import { useMockDetectionWebSocket } from '@/composables/useDetectionWebSocket'
import { useMockFireWebSocket } from '@/composables/useFireWebSocket'
import { useDetectionStore } from '@/stores/detection'
import { useFireStore } from '@/stores/fire'

const positionStore = usePositionStore()
const { hasTarget, target } = storeToRefs(positionStore)

const detectionStore = useDetectionStore()
const fireStore = useFireStore()

// Mock Position WebSocket
const mockPositionWs = useMockPositionWebSocket()
const isMoving = ref(false)

// Mock Fire WebSocket
const mockFireWs = useMockFireWebSocket()

// Mock Detection WebSocket (Fire WebSocket 연결)
const mockDetectionWs = useMockDetectionWebSocket(mockFireWs)
const isDetecting = ref(false)

// Mock Target Command
const { isSending, error, sendTarget } = useMockTargetCommand(mockPositionWs)

/**
 * 테스트 실행 버튼
 * 1. Position WebSocket 시작 (전차 이동)
 * 2. Detection WebSocket 시작 (객체 탐지 + 자동 발포)
 * 3. 타겟 전송 (API 호출)
 */
async function handleTestExecute() {
  // 1. Position WebSocket 시작
  const success = await sendTarget()
  
  if (success) {
    isMoving.value = true
    console.log(' Position 테스트 실행')
  } else {
    console.error('❌ 실행 실패:', error.value)
  }
  
  // 2. Detection WebSocket 시작 (적 전차 발견 시 자동 발포)
  mockDetectionWs.start()
  isDetecting.value = true
  console.log(' Detection + Fire 테스트 실행')
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
  
  // 발포 기록 초기화
  fireStore.clearFires()
  
  console.log(' 테스트 정지')
}
</script>

<template>
  <div class="p-3 bg-gray-100 border-2 border-dashed border-red-400 rounded-lg flex flex-row items-center gap-6">
    <h3 class="text-sm font-bold text-red-500 mr-4 whitespace-nowrap">테스트 컨트롤</h3>
    <!-- 버튼 -->
    <div class="flex gap-2">
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
    <div class="text-xs space-y-1 ml-6">
      <span class="mr-4">전차 이동: <span :class="isMoving ? 'text-green-600' : 'text-gray-500'">{{ isMoving ? '진행 중' : '정지' }}</span></span>
      <span class="mr-4">객체 탐지: <span :class="isDetecting ? 'text-green-600' : 'text-gray-500'">{{ isDetecting ? '진행 중' : '정지' }}</span></span>
      <span class="mr-4">목표 설정: <span :class="hasTarget ? 'text-blue-600' : 'text-gray-500'">{{ hasTarget ? `(${target?.x}, ${target?.y})` : '미설정' }}</span></span>
      <span v-if="error" class="text-red-500 font-bold ml-2">{{ error }}</span>
    </div>
  </div>
</template>