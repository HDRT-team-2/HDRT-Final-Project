import { ref } from 'vue'
import { defineStore } from 'pinia'
import type { FireEvent, FireResponse, FireResult } from '@/types/fire'
import { useDetectionStore } from './detection-store'

export const useFireStore = defineStore('fire', () => {
  // State-----------------------------------------
  
  // 모든 발포 이벤트
  const fires = ref<FireEvent[]>([])

  // Actions---------------------------------------
  
  // 발포 이벤트 추가
  function addFire(data: FireResponse) {
    
    // detection-store에서 target_tracking_id로 객체 찾기
    const detectionStore = useDetectionStore()
    const targetObject = detectionStore.objects.find(
      obj => obj.tracking_id === data.target_tracking_id
    )
        
    // 찾은 객체의 class_name 사용, 없으면 'other'
    const target_class_name = targetObject?.class_name || 'other'
    
    const newFire: FireEvent = {
      id: `fire-${data.target_tracking_id}-${Date.now()}`,
      ally_id: data.ally_id,
      target_tracking_id: data.target_tracking_id,
      target_class_name,
      firedAt: new Date(),
    }
    
    fires.value.push(newFire)
  }
  
  // 명중 결과 업데이트
  function updateFireResult(targetTrackingId: number, result: FireResult) {
    const fire = fires.value.find(f => f.target_tracking_id === targetTrackingId && !f.result)
    if (fire) {
      fire.result = result
    }
  }
  
  // 전체 초기화
  function clearFires() {
    fires.value = []
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