<script setup lang="ts">
import { ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import type { TankPosition } from '@/types/position'
import type { DetectedObject } from '@/types/detection'
import { useFireStore } from '@/stores/fire-store'
import { useDetectionStore } from '@/stores/detection-store'

interface Props {
  myTanks: TankPosition[]
  coordToSvg: (x: number, y: number) => { x: number; y: number }
}

const props = defineProps<Props>()

const fireStore = useFireStore()
const { fires } = storeToRefs(fireStore)
const detectionStore = useDetectionStore()
const { objects } = storeToRefs(detectionStore)

// 포물선 애니메이션 데이터
interface TrajectoryArc {
  id: string
  path: string
  opacity: number
}

const activeArcs = ref<TrajectoryArc[]>([])

// 포물선 경로 생성 (2차 베지어 곡선)
function createArcPath(startX: number, startY: number, endX: number, endY: number): string {
  // 중간 지점 계산
  const midX = (startX + endX) / 2
  const midY = (startY + endY) / 2
  
  // 거리 계산
  const distance = Math.sqrt((endX - startX) ** 2 + (endY - startY) ** 2)
  
  // 포물선 높이 (거리에 비례, 위로 올라감)
  const arcHeight = distance * 0.3
  
  // 제어점 (중간 지점에서 위로)
  const controlX = midX
  const controlY = midY - arcHeight
  
  // SVG path: M(시작) Q(제어점, 끝점)
  return `M ${startX} ${startY} Q ${controlX} ${controlY} ${endX} ${endY}`
}

// fire 이벤트 감지 및 포물선 생성
watch(fires, (newFires, oldFires) => {
  // 새로 추가된 fire 이벤트 찾기
  const addedFires = newFires.filter(newFire => 
    !oldFires?.some(oldFire => oldFire.id === newFire.id)
  )
  
  addedFires.forEach(fire => {
    // ally_id로 아군 위치 찾기
    const allyTank = props.myTanks.find(tank => tank.tank_id === fire.ally_id)
    if (!allyTank) {
      console.warn(`아군 탱크 [${fire.ally_id}]를 찾을 수 없음`)
      return
    }
    
    // target_tracking_id로 적 위치 찾기
    const targetObject = objects.value.find(obj => obj.tracking_id === fire.target_tracking_id)
    if (!targetObject) {
      console.warn(`대상 객체 [${fire.target_tracking_id}]를 찾을 수 없음`)
      return
    }
    
    // 좌표를 SVG 좌표로 변환
    const startSvg = props.coordToSvg(allyTank.x, allyTank.y)
    const endSvg = props.coordToSvg(targetObject.position.x, targetObject.position.y)
    
    // 포물선 경로 생성
    const path = createArcPath(startSvg.x, startSvg.y, endSvg.x, endSvg.y)
    
    // 애니메이션 추가
    const arc: TrajectoryArc = {
      id: fire.id,
      path,
      opacity: 1
    }
    
    activeArcs.value.push(arc)
    
    // 1.5초 후 페이드아웃 시작
    setTimeout(() => {
      const arcIndex = activeArcs.value.findIndex(a => a.id === arc.id)
      if (arcIndex !== -1) {
        // 페이드아웃 애니메이션 (0.5초)
        const fadeInterval = setInterval(() => {
          const currentArc = activeArcs.value[arcIndex]
          if (currentArc) {
            currentArc.opacity -= 0.1
            if (currentArc.opacity <= 0) {
              clearInterval(fadeInterval)
              activeArcs.value.splice(arcIndex, 1)
            }
          } else {
            clearInterval(fadeInterval)
          }
        }, 50)
      }
    }, 1500)
  })
}, { deep: true })
</script>

<template>
  <!-- 포물선 애니메이션 -->
  <g v-for="arc in activeArcs" :key="arc.id">
    <path
      :d="arc.path"
      fill="none"
      stroke="#ff4444"
      stroke-width="3"
      :opacity="arc.opacity"
      stroke-linecap="round"
    />
  </g>
</template>
