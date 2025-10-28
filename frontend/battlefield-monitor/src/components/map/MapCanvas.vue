<script setup lang="ts">
import type { TankPosition, TargetPosition } from '@/types/position'
import type { DetectedObject } from '@/types/detection'

interface Props {
  current: TankPosition    // 내 위치
  target: TargetPosition | null  // 목표 위치
  objects: DetectedObject[]      // 탐지된 객체들
}

const props = defineProps<Props>()

// SVG 캔버스 크기 (픽셀)
const canvasWidth = 740  // px
const canvasHeight = 740 // px

// 좌표계 범위
const coordWidth = 300   // 0~300
const coordHeight = 300  // 0~300

// 좌표 → SVG 변환
function coordToSvg(x: number, y: number) {
  return {
    x: (x / coordWidth) * canvasWidth,
    y: ((coordHeight - y) / coordHeight) * canvasHeight
  }
}

// 클래스별 색상
function getObjectColor(className: string) {
  switch (className) {
    case 'tank': return '#dc2626'    // 빨강 (적 전차)
    case 'person': return '#3b82f6'  // 파랑 (민간인)
    case 'car': return '#3b82f6'     // 파랑 (민간 차량)
    case 'truck': return '#3b82f6'   // 파랑 (민간 트럭)
    default: return '#6b7280'        // 회색
  }
}

// 클래스별 아이콘 (간단한 도형)
function getObjectShape(className: string) {
  switch (className) {
    case 'tank': return 'rect'       // 사각형
    case 'person': return 'circle'   // 원
    case 'car': return 'rect'        // 사각형
    case 'truck': return 'rect'      // 사각형
    default: return 'circle'
  }
}
</script>

<template>
  <svg 
    :width="canvasWidth" 
    :height="canvasHeight"
    class="border-2 border-gray-400 bg-gray-50"
    :viewBox="`0 0 ${canvasWidth} ${canvasHeight}`"
  >
    <!-- 배경 그리드 -->
    <defs>
      <pattern id="grid" width="74" height="74" patternUnits="userSpaceOnUse">
        <path 
          d="M 60 0 L 0 0 0 60" 
          fill="none" 
          stroke="gray" 
          stroke-width="0.5"
          opacity="0.3"
        />
      </pattern>
    </defs>
    <rect width="100%" height="100%" fill="url(#grid)" />
    
    <!-- 좌표 텍스트 (모서리) -->
    <text x="5" y="15" font-size="12" fill="gray">(0,300)</text>
    <text :x="canvasWidth - 55" y="15" font-size="12" fill="gray">(300,300)</text>
    <text x="5" :y="canvasHeight - 5" font-size="12" fill="gray">(0,0)</text>
    <text :x="canvasWidth - 55" :y="canvasHeight - 5" font-size="12" fill="gray">(300,0)</text>

    <!-- 목표 위치 (있으면) -->
    <g v-if="target">
      <circle 
        :cx="coordToSvg(target.x, target.y).x"
        :cy="coordToSvg(target.x, target.y).y"
        r="8"
        fill="none"
        stroke="#10b981"
        stroke-width="3"
        opacity="0.8"
      />
      <circle 
        :cx="coordToSvg(target.x, target.y).x"
        :cy="coordToSvg(target.x, target.y).y"
        r="3"
        fill="#10b981"
      />
      <text 
        :x="coordToSvg(target.x, target.y).x + 12"
        :y="coordToSvg(target.x, target.y).y + 5"
        font-size="11"
        fill="#10b981"
        font-weight="bold"
      >
        목표
      </text>
    </g>
    
    <!-- 탐지된 객체들 -->
    <g v-for="obj in objects" :key="obj.tracking_id">
      <!-- 적 전차 (사각형) -->
      <g v-if="obj.class_name === 'tank'">
        <rect
          :x="coordToSvg(obj.position.x, obj.position.y).x - 6"
          :y="coordToSvg(obj.position.x, obj.position.y).y - 6"
          width="12"
          height="12"
          :fill="getObjectColor(obj.class_name)"
        />
        <text 
          :x="coordToSvg(obj.position.x, obj.position.y).x + 10"
          :y="coordToSvg(obj.position.x, obj.position.y).y + 4"
          font-size="10"
          fill="#dc2626"
          font-weight="bold"
        >
          {{ obj.tracking_id }}
        </text>
      </g>
      
      <!-- 민간인/차량 (원) -->
      <g v-else>
        <circle
          :cx="coordToSvg(obj.position.x, obj.position.y).x"
          :cy="coordToSvg(obj.position.x, obj.position.y).y"
          r="5"
          :fill="getObjectColor(obj.class_name)"
          opacity="0.7"
        />
        <text 
          :x="coordToSvg(obj.position.x, obj.position.y).x + 8"
          :y="coordToSvg(obj.position.x, obj.position.y).y + 4"
          font-size="9"
          fill="#3b82f6"
        >
          {{ obj.tracking_id }}
        </text>
      </g>
    </g>
    
    <!-- 내 전차 위치 (마지막에 그려서 맨 위에 표시) -->
    <g>
      <circle 
        :cx="coordToSvg(current.x, current.y).x"
        :cy="coordToSvg(current.x, current.y).y"
        r="10"
        fill="#22c55e"
        stroke="#fff"
        stroke-width="2"
      />
      <text 
        :x="coordToSvg(current.x, current.y).x + 15"
        :y="coordToSvg(current.x, current.y).y + 5"
        font-size="12"
        fill="#22c55e"
        font-weight="bold"
      >
        아군
      </text>
    </g>
  </svg>
</template>

<style scoped>
svg {
  display: block;
  margin: 0 auto;
}
</style>