import { ref } from 'vue'
import { defineStore } from 'pinia'
import type { FireEvent, FireResponse, FireResult } from '@/types/fire'
import { CLASS_ID_TO_NAME } from '@/types/detection'

export const useFireStore = defineStore('fire', () => {
  // State-----------------------------------------
  
  // 모든 발포 이벤트
  const fires = ref<FireEvent[]>([])

  // Actions---------------------------------------
  
  // 발포 이벤트 추가
  function addFire(data: FireResponse) {
    // class_id를 class_name으로 변환
    const target_class_name = CLASS_ID_TO_NAME[data.class_id] || 'other'
    
    const newFire: FireEvent = {
      id: `fire-${data.target_tracking_id}-${Date.now()}`,
      ally_id: data.ally_id,
      target_tracking_id: data.target_tracking_id,
      target_class_name,
      firedAt: new Date(),
    }
    
    fires.value.push(newFire)
    console.log(`발사: 아군 [${data.ally_id}] → 대상 [${data.target_tracking_id}] (${target_class_name})`)
  }
  
  // 명중 결과 업데이트
  function updateFireResult(targetTrackingId: number, result: FireResult) {
    const fire = fires.value.find(f => f.target_tracking_id === targetTrackingId && !f.result)
    if (fire) {
      fire.result = result
      console.log(`명중 결과 업데이트: 대상 [${targetTrackingId}] - ${result}`)
    }
  }
  
  // 전체 초기화
  function clearFires() {
    fires.value = []
    console.log('모든 발포 기록 삭제')
  }

  // Return---------------------------------------
  return {
    // State
    fires,
    
    // Actions
    addFire,
    updateFireResult,
    clearFires,
  }
})