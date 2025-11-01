import { ref } from 'vue'
import { defineStore } from 'pinia'
import type { FireEvent, FireResponse, HitResultResponse, HitResult } from '@/types/fire'

export const useFireStore = defineStore('fire', () => {
  // State-----------------------------------------
  
  // 모든 발포 이벤트
  const fires = ref<FireEvent[]>([])

  // Actions---------------------------------------
  
  // 발포 이벤트 추가
  function addFire(data: FireResponse) {
    const newFire: FireEvent = {
      id: `fire-${data.target_tracking_id}-${Date.now()}`,
      target_tracking_id: data.target_tracking_id,
      firedAt: data.timestamp ? new Date(data.timestamp) : new Date(),
    }
    
    fires.value.push(newFire)
    console.log(`발포: 대상 [${data.target_tracking_id}]`)
  }
  
  // 전체 초기화
  function clearFires() {
    fires.value = []
    console.log(' 모든 발포 기록 삭제')
  }

  // Return---------------------------------------
  return {
    // State
    fires,
    
    // Actions
    addFire,
    clearFires,
  }
})