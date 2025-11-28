import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import type { TankPosition } from '@/types/position'

export const usePositionStore = defineStore('position', () => {
  // State---------------------------------------
  
  // 아군 탱크들의 위치 배열
  const myTanks = ref<TankPosition[]>([])

  // Computed-----------------------------------
  
  // 현재 위치 (모든 탱크의 평균 위치)
  const current = computed(() => {
    if (myTanks.value.length === 0) {
      return { x: 0, y: 0 }
    }
    
    const avgX = myTanks.value.reduce((sum, tank) => sum + tank.x, 0) / myTanks.value.length
    const avgY = myTanks.value.reduce((sum, tank) => sum + tank.y, 0) / myTanks.value.length
    
    return { x: avgX, y: avgY }
  })

  // Actions-------------------------------------
  
  // 탱크 위치 업데이트 (WebSocket에서 호출)
  function updateTankPosition(data: TankPosition) {
    const existing = myTanks.value.find(t => t.tank_id === data.tank_id)
    
    if (existing) {
      existing.x = data.x
      existing.y = data.y
    } else {
      myTanks.value.push(data)
    }
  }

  // Return (외부에 노출)
  return {
    // State
    myTanks,
    
    // Computed
    current,
    
    // Actions
    updateTankPosition,
  }
})