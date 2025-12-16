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

// 이미 처리한 fire ID를 추적
const processedFireIds = ref<Set<string>>(new Set())

// fire 이벤트 감지 및 포물선 생성
watch(fires, (newFires) => {
  // 아직 처리하지 않은 fire 이벤트 찾기
  const addedFires = newFires.filter(fire => !processedFireIds.value.has(fire.id))
  
  addedFires.forEach(fire => {
    // 처리 목록에 추가
    processedFireIds.value.add(fire.id)
    
    console.log('[TrajectoryArcs] Fire 이벤트:', { 
      ally_id: fire.ally_id, 
      target_tracking_id: fire.target_tracking_id,
      myTanks: props.myTanks.map(t => ({ tank_id: t.tank_id, x: t.x, y: t.y }))
    })
    
    // 포물선 생성 시도 함수
    const tryCreateArc = () => {
      // ally_id로 아군 위치 찾기
      const allyTank = props.myTanks.find(tank => String(tank.tank_id) === String(fire.ally_id))
      if (!allyTank) {
        console.warn('[TrajectoryArcs] 아군 탱크를 찾을 수 없음. ally_id:', fire.ally_id)
        return false
      }
      console.log('[TrajectoryArcs] 아군 탱크 찾음:', allyTank)
      
      // target_tracking_id로 적 위치 찾기 (string으로 비교)
      const targetObject = objects.value.find(obj => String(obj.tracking_id) === String(fire.target_tracking_id))
      if (!targetObject) {
        console.warn('[TrajectoryArcs] 타겟 객체를 찾을 수 없음. target_tracking_id:', fire.target_tracking_id)
        return false
      }
      console.log('[TrajectoryArcs] 타겟 객체 찾음:', targetObject)
    
      // 좌표를 SVG 좌표로 변환
      const startSvg = props.coordToSvg(allyTank.x, allyTank.y)
      const endSvg = props.coordToSvg(targetObject.position.x, targetObject.position.y)
      
      // 포물선 경로 생성
      const path = createArcPath(startSvg.x, startSvg.y, endSvg.x, endSvg.y)
      
      console.log('[TrajectoryArcs] 포물선 생성:', {
        from: startSvg,
        to: endSvg,
        path
      })
      
      // 애니메이션 추가
      const arc: TrajectoryArc = {
        id: fire.id,
        path,
        opacity: 1
      }
      
      activeArcs.value.push(arc)
      console.log('[TrajectoryArcs] activeArcs 추가됨. 현재 개수:', activeArcs.value.length)
      
      // 0.7초 후 페이드아웃 시작
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
      }, 700)
      
      return true
    }
    
    // 즉시 시도
    if (!tryCreateArc()) {
      // 실패하면 50ms 후 재시도 (최대 3회)
      let retryCount = 0
      const retryInterval = setInterval(() => {
        retryCount++
        if (tryCreateArc() || retryCount >= 3) {
          clearInterval(retryInterval)
          if (retryCount >= 3) {
            console.error('[TrajectoryArcs] 포물선 생성 실패 (3회 재시도)', fire)
          }
        }
      }, 50)
    }
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
