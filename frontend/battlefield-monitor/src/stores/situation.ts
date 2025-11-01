import { ref, computed, watch } from 'vue'
import { defineStore } from 'pinia'
import { useDetectionStore } from './detection'
import { useFireStore } from './fire'
import type { SituationEvent } from '@/types/situation'
import { CLASS_NAME_KR } from '@/types/detection'

export const useSituationStore = defineStore('situation', () => {
  const detectionStore = useDetectionStore()
  const fireStore = useFireStore()
  
  // State------------------------------------------
  
  const events = ref<SituationEvent[]>([]) // 이벤트 배열 (State)
  const maxEvents = ref(100) // 최대 이벤트 개수
  
  // 추적용: 이미 추가된 이벤트 ID
  const addedDetectionIds = ref(new Set<number>())
  const addedFireIds = ref(new Set<string>())

  // Computed---------------------------------------
  
  // 최신 이벤트 (첫 번째)
  const latestEvent = computed(() => events.value[0] || null)

  // Actions---------------------------------------
  
  // 이벤트 추가 (맨 앞에)
  function addEvent(event: SituationEvent) {
    events.value.unshift(event)
    
    // 최대 개수 초과 시 오래된 이벤트 제거
    if (events.value.length > maxEvents.value) {
      events.value = events.value.slice(0, maxEvents.value)
    }
    
    console.log(`상황 로그: ${event.message}`)
  }
  
  // 최대 이벤트 개수 설정
  function setMaxEvents(max: number) {
    maxEvents.value = max
  }
  
  // 전체 초기화
  function clearEvents() {
    events.value = []
    addedDetectionIds.value.clear()
    addedFireIds.value.clear()
    console.log('🗑️ 모든 상황 로그 삭제')
  }

  // Watch: Detection Store 감시 --------------------------------
  watch(
    () => detectionStore.objects,
    (newObjects) => {
      newObjects.forEach(obj => {
        // 이미 추가된 객체는 스킵
        if (addedDetectionIds.value.has(obj.tracking_id)) return
        
        // 새 탐지 이벤트 추가
        addEvent({
          id: `detection-${obj.tracking_id}`,
          type: 'detection',
          time: obj.detectedAt,
          tracking_id: obj.tracking_id,
          className: obj.class_name,
          message: `${CLASS_NAME_KR[obj.class_name]} 탐지 [ID: ${obj.tracking_id}]`
        })
        
        addedDetectionIds.value.add(obj.tracking_id)
      })
    },
    { deep: true }
  )

  // Watch: Fire Store 감시 --------------------------------  
  watch(
    () => fireStore.fires,
    (newFires) => {
      newFires.forEach(fire => {
        // 발포 이벤트
        const fireEventId = `fire-${fire.id}`
        if (!addedFireIds.value.has(fireEventId)) {
          addEvent({
            id: fireEventId,
            type: 'fire',
            time: fire.firedAt,
            tracking_id: fire.target_tracking_id,
            message: `발포 [대상: ${fire.target_tracking_id}]`
          })
          addedFireIds.value.add(fireEventId)
        }
      })
    },
    { deep: true }
  )

  // Return
  return {
    // State
    events,
    maxEvents,
    
    // Computed
    latestEvent,
    
    // Actions
    addEvent,
    setMaxEvents,
    clearEvents
  }
})