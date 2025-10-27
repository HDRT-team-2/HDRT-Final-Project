import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import type { TankPosition, TargetPosition, TankStatus } from '@/types/position'

export const usePositionStore = defineStore('position', () => {
  // State (ref로 선언)
  
  // 현재 위치 (WebSocket으로 업데이트예정)
  const current = ref<TankPosition>({
    x: 150,
    y: 150,
    angle: 0
  })

  // 목표 위치 (사용자 입력 또는 지도 클릭으로 변경 예정)
  const target = ref<TargetPosition | null>(null)


  // Computed (계산된 값)
  
  // 목표가 설정되어 있는지 확인
  const hasTarget = computed(() => target.value !== null)

  // Actions (함수)
  
  // 현재 위치 업데이트 (WebSocket에서 호출 예정)
  function updateCurrentPosition(position: TankPosition) {
    current.value = position
  }

  // 현재 위치 부분 업데이트
  function setCurrentPosition(x: number, y: number, angle?: number) {
    current.value.x = x
    current.value.y = y
    if (angle !== undefined) {
      current.value.angle = angle
    }
  }

  //목표 위치 설정 (TargetInput 또는 Map에서 호출)
  function setTarget(x: number, y: number) {
    target.value = {
      x,
      y,
      setAt: new Date()
    }
  }

  // 목표 위치 초기화
  function clearTarget() {
    target.value = null
  }

  /**
   * Store 초기화 (테스트용)
   */
  function reset() {
    current.value = { x: 150, y: 150, angle: 0 }
    target.value = null
  }

  // Return (외부에 노출)
  return {
    // State
    current,
    target,
    
    // Computed
    hasTarget,
    
    // Actions
    updateCurrentPosition,
    setCurrentPosition,
    setTarget,
    clearTarget,
    reset
  }
})