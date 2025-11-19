import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import type { DetectedObject, DetectionResponse, ObjectClassName } from '@/types/detection'
import { CLASS_ID_TO_NAME } from '@/types/detection'

export const useDetectionStore = defineStore('detection', () => {

  // State----------------------------------------
  
  // 탐지된 모든 객체
  const objects = ref<DetectedObject[]>([])

  // Computed-------------------------------------

  // 클래스별 객체 수
  const classCounts = computed(() => {
    const counts: Record<ObjectClassName, number> = {
      human: 0,
      tank: 0,
      car: 0,
      truck: 0,
      mine: 0,
      other: 0,
      rock_small: 0,
      rock_large: 0,
      wall: 0
    }
    
    objects.value.forEach(obj => {
      counts[obj.class_name]++
    })
    
    return counts
  })

  // 적 전차 수
  const enemyTankCount = computed(() => classCounts.value.tank)
  
  // 적 보병 수
  const enemyInfantryCount = computed(() => classCounts.value.human)
  
  // 총 적 객체 수
  const enemyCount = computed(() => 
    enemyTankCount.value + 
    enemyInfantryCount.value
  )

  // 아군 전차 수 (임의 설정: 아직 클래스 없음)
  const allyTankCount = computed(() => 0)
  
  // 아군 보병 수 (임의 설정: 아직 클래스 없음)
  const allyInfantryCount = computed(() => 0)
  
  // 총 아군 객체 수
  const allyCount = computed(() => 
    allyTankCount.value + 
    allyInfantryCount.value
  )

  // 기타 - 차량 (car + truck)
  const vehicleCount = computed(() =>
    classCounts.value.car + classCounts.value.truck
  )
  
  // 기타 - 바위 (rock_small + rock_large)
  const rockCount = computed(() =>
    classCounts.value.rock_small + classCounts.value.rock_large
  )
  
  // 총 기타 객체 수
  const otherCount = computed(() => 
    vehicleCount.value + 
    rockCount.value
  )

  // 객체 탐지 수
  const totalCount = computed(() => objects.value.length)

  // Actions ------------------------------------------
  
  // 백엔드 데이터를 DetectedObject로 변환

  function parseDetectionResponse(data: DetectionResponse): DetectedObject {
    const class_name = CLASS_ID_TO_NAME[data.class_id] || 'human'
    
    return {
      tracking_id: data.tracking_id,
      class_id: data.class_id,
      class_name,
      position: {
        x: data.x,
        y: data.y
      },
      detectedAt: new Date(),
      lastUpdated: new Date()
    }
  }
  
  /**
   * 탐지 객체 추가 또는 업데이트 (단일)
   * - 같은 tracking_id → 위치 업데이트
   * - 새로운 tracking_id → 새 객체 추가
   */
  function updateObject(data: DetectionResponse) {
    const existing = objects.value.find(
      obj => obj.tracking_id === data.tracking_id
    )
    
    if (existing) {
      // 기존 객체 위치 업데이트
      existing.position.x = data.x
      existing.position.y = data.y
      existing.lastUpdated = new Date()
      
      console.log(`객체 업데이트 [${data.tracking_id}]:`, existing.class_name, existing.position)
    } else {
      // 새 객체 추가
      const newObj = parseDetectionResponse(data)
      objects.value.push(newObj)
      
      console.log(`새 객체 발견 [${data.tracking_id}]:`, newObj.class_name, newObj.position)
    }
  }
  
  /**
   * 탐지 객체 일괄 업데이트 (WebSocket에서 호출)
   * - 각 객체마다 추가 또는 업데이트
   */
  function updateObjects(dataList: DetectionResponse[]) {
    dataList.forEach(data => {
      updateObject(data)
    })
    
    console.log(`탐지 업데이트: 총 ${objects.value.length}개 객체`)
  }
  
  /**
   * 전체 초기화
   */
  function clearObjects() {
    objects.value = []
    console.log('모든 객체 제거')
  }
  
  /**
   * Store 초기화 (테스트용)
   */
  function reset() {
    objects.value = []
  }

  // Return-Values -----------------------------------
  return {
    // State
    objects,
    
    // Computed
    classCounts,
    enemyTankCount,
    enemyInfantryCount,
    enemyCount,
    allyTankCount,
    allyInfantryCount,
    allyCount,
    vehicleCount,
    rockCount,
    otherCount,
    totalCount,
    
    // Actions
    updateObject,
    updateObjects,
    clearObjects,
    reset
  }
})