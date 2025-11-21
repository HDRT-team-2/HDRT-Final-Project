<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { storeToRefs } from 'pinia'
import type { TankPosition } from '@/types/position'
import type { DetectedObject } from '@/types/detection'
import { useMapStore } from '@/stores/map-store'
import { useStatusReportStore } from '@/stores/mission-status-store'
import { useTargetCommand } from '@/composables/useTargetCommand'

import MyTankIcon from '@/components/icons/MyTankIcon.vue'
import GoalIcon from '@/components/icons/GoalIcon.vue'
import TrajectoryArcs from './TrajectoryArcs.vue'
import DetectedObjects from './DetectedObjects.vue'

const mapStore = useMapStore()
const { currentMapImage } = storeToRefs(mapStore)
const statusReportStore = useStatusReportStore()
const { sendTarget } = useTargetCommand()

// 'a' 키 눌림 상태 추적
const isAKeyPressed = ref(false)

// 키보드 이벤트 리스너
function handleKeyDown(event: KeyboardEvent) {
  if (event.key === 'a' || event.key === 'A') {
    isAKeyPressed.value = true
  }
}

function handleKeyUp(event: KeyboardEvent) {
  if (event.key === 'a' || event.key === 'A') {
    isAKeyPressed.value = false
  }
}

// 컴포넌트 마운트 시 키보드 리스너 등록
onMounted(() => {
  window.addEventListener('keydown', handleKeyDown)
  window.addEventListener('keyup', handleKeyUp)
})

// 컴포넌트 언마운트 시 리스너 제거
onUnmounted(() => {
  window.removeEventListener('keydown', handleKeyDown)
  window.removeEventListener('keyup', handleKeyUp)
})

interface Props {
  myTanks: TankPosition[]            // 아군 탱크들
  target: { x: number; y: number } | null      // 목표 위치 (백엔드 확정)
  objects: DetectedObject[]          // 탐지된 객체들
}

const props = defineProps<Props>()

// SVG 캔버스 크기 (픽셀)
const canvasWidth = 900  // px
const canvasHeight = 900 // px

// 좌표계 범위
const coordWidth = 300   // 0~300
const coordHeight = 300  // 0~300

// 좌표 → SVG 변환 (Y축 반전)
function coordToSvg(x: number, y: number) {
  return {
    x: (x / coordWidth) * canvasWidth,
    y: ((coordHeight - y) / coordHeight) * canvasHeight  // Y축 반전
  }
}

// SVG → 좌표 변환 (Y축 반전)
function svgToCoord(svgX: number, svgY: number) {
  return {
    x: (svgX / canvasWidth) * coordWidth,
    y: coordHeight - (svgY / canvasHeight) * coordHeight  // Y축 반전
  }
}

// 우클릭 핸들러
// @contextmenu: 우클릭 이벤트
// preventDefault(): 브라우저 기본 컨텍스트 메뉴를 막음
function handleContextMenu(event: MouseEvent) {
  event.preventDefault() // 우클릭 시 나오는 브라우저 메뉴 막기
  
  // SVG 내 클릭 위치 계산
  const svg = event.currentTarget as SVGSVGElement
  const rect = svg.getBoundingClientRect()
  const svgX = ((event.clientX - rect.left) / rect.width) * canvasWidth
  const svgY = ((event.clientY - rect.top) / rect.height) * canvasHeight
  
  // SVG 좌표 → 게임 좌표 변환
  const coord = svgToCoord(svgX, svgY)
  
  // 'a'키 눌린 상태에 따라 mission 결정
  const mission = isAKeyPressed.value ? 'attack_n_search' : 'defend'
  
  // mission-status store에 명령 target 설정
  statusReportStore.setCommandTarget(coord.x, coord.y, mission)
  
  console.log(`목표 설정: (${coord.x.toFixed(2)}, ${coord.y.toFixed(2)}), mission: ${mission}`)
  
  // 즉시 백엔드로 전송
  sendTarget()
}

</script>

<template>
  <svg 
    class="w-full h-full"
    :viewBox="`0 0 ${canvasWidth} ${canvasHeight}`"
    preserveAspectRatio="xMidYMid meet"
    @contextmenu="handleContextMenu"
  >
    <!-- 배경 이미지 -->
    <defs>
      <pattern id="mapBackground" x="0" y="0" width="1" height="1">
        <image 
          :href="currentMapImage" 
          :width="canvasWidth" 
          :height="canvasHeight" 
          preserveAspectRatio="xMidYMid slice"
        />
      </pattern>
      <pattern id="grid" width="74" height="74" patternUnits="userSpaceOnUse">
        <path 
          d="M 74 0 L 0 0 0 74" 
          fill="none" 
          stroke="gray" 
          stroke-width="0.5"
          opacity="0.3"
        />
      </pattern>
    </defs>
    <!-- 배경 이미지 적용 -->
    <rect width="100%" height="100%" fill="url(#mapBackground)" />
    <!-- 그리드 오버레이 -->
    <rect width="100%" height="100%" fill="url(#grid)" />
    
    <!-- 포물선 애니메이션 -->
    <TrajectoryArcs :my-tanks="myTanks" :coord-to-svg="coordToSvg" />
    
    <!-- 목표 위치 (있으면) -->
    <GoalIcon
      v-if="target"
      :x="coordToSvg(target.x, target.y).x"
      :y="coordToSvg(target.x, target.y).y"
      :size="8"
    />
    
    <!-- 탐지된 객체들 -->
    <DetectedObjects :objects="objects" :coord-to-svg="coordToSvg" />
    
    <!-- 내 전차들 위치 (마지막에 그려서 맨 위에 표시) -->
    <g v-for="tank in myTanks" :key="tank.tank_id">
      <MyTankIcon
        :x="coordToSvg(tank.x, tank.y).x"
        :y="coordToSvg(tank.x, tank.y).y"
        :size="18"
      />
    </g>
  </svg>
</template>

<style scoped>
svg {
  display: block;
  margin: 0 auto;
}
</style>