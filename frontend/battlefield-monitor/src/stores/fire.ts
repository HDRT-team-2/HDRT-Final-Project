import { ref } from 'vue'
import { defineStore } from 'pinia'
import type { FireEvent, FireResponse, HitResultResponse, HitResult } from '@/types/fire'

export const useFireStore = defineStore('fire', () => {
  // ==========================================
  // State
  // ==========================================
  
  // 모든 발포 이벤트
  const fires = ref<FireEvent[]>([])

  // ==========================================
  // Computed
  // ==========================================
  
  // (필요 없음 - UI에서 직접 fires 배열 사용)

  // ==========================================
  // Actions
  // ==========================================
  
  /**
   * 발포 이벤트 추가
   */
  function addFire(data: FireResponse) {
    const newFire: FireEvent = {
      id: `fire-${data.target_tracking_id}-${Date.now()}`,
      target_tracking_id: data.target_tracking_id,
      firedAt: data.timestamp ? new Date(data.timestamp) : new Date(),
      hitResult: undefined // 아직 결과 없음
    }
    
    fires.value.push(newFire)
    console.log(`🔫 발포: 대상 [${data.target_tracking_id}]`)
  }
  
  /**
   * 명중 결과 업데이트
   * - target_tracking_id로 발포 이벤트를 찾아서 결과 업데이트
   */
  function updateHitResult(data: HitResultResponse) {
    // 가장 최근 발포 이벤트 중에서 결과가 없는 것 찾기
    const fire = fires.value
      .filter(f => f.target_tracking_id === data.target_tracking_id)
      .filter(f => f.hitResult === undefined)
      .sort((a, b) => b.firedAt.getTime() - a.firedAt.getTime())[0]
    
    if (fire) {
      fire.hitResult = {
        hit: data.hit,
        hitAt: data.timestamp ? new Date(data.timestamp) : new Date()
      }
      
      const result = data.hit ? '🎯 명중!' : '❌ 미명중'
      console.log(`${result} 대상 [${data.target_tracking_id}]`)
    } else {
      console.warn(`⚠️ 발포 이벤트를 찾을 수 없음: tracking_id ${data.target_tracking_id}`)
    }
  }
  
  /**
   * 전체 초기화
   */
  function clearFires() {
    fires.value = []
    console.log('🗑️ 모든 발포 기록 삭제')
  }
  
  /**
   * Store 초기화 (테스트용)
   */
  function reset() {
    fires.value = []
  }

  // ==========================================
  // Return
  // ==========================================
  return {
    // State
    fires,
    
    // Actions
    addFire,
    updateHitResult,
    clearFires,
    reset
  }
})