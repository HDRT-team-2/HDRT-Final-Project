<script setup lang="ts">
import { computed } from 'vue'
import type { TankPosition, TargetPosition } from '@/types/position'
import type { DetectedObject } from '@/types/detection'

import MyTankIcon from '@/components/icons/MyTankIcon.vue'
import EnemyIcon from '@/components/icons/EnemyIcon.vue'
import CarIcon from '@/components/icons/CarIcon.vue'
import PersonIcon from '@/components/icons/PersonIcon.vue'

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

// 좌표 → SVG 변환 (Y축 반전)
function coordToSvg(x: number, y: number) {
  return {
    x: (x / coordWidth) * canvasWidth,
    y: ((coordHeight - y) / coordHeight) * canvasHeight  // Y축 반전
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
          d="M 74 0 L 0 0 0 74" 
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
    <text :x="canvasWidth - 75" y="15" font-size="12" fill="gray">(300,300)</text>
    <text x="5" :y="canvasHeight - 5" font-size="12" fill="gray">(0,0)</text>
    <text :x="canvasWidth - 75" :y="canvasHeight - 5" font-size="12" fill="gray">(300,0)</text>
    
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
       <EnemyIcon 
        v-if="obj.class_name === 'tank'"
        :x="coordToSvg(obj.position.x, obj.position.y).x"
        :y="coordToSvg(obj.position.x, obj.position.y).y"
        :size="12"
      />

      <!-- 민간인/차량 (원) -->
       <PersonIcon 
        v-else-if="obj.class_name === 'person'"
        :x="coordToSvg(obj.position.x, obj.position.y).x"
        :y="coordToSvg(obj.position.x, obj.position.y).y"
        :size="8"
      />
      <CarIcon 
        v-else-if="obj.class_name === 'car' || obj.class_name === 'truck'"
        :x="coordToSvg(obj.position.x, obj.position.y).x"
        :y="coordToSvg(obj.position.x, obj.position.y).y"
        :size="10"
      />
    </g>
    
    <!-- 내 전차 위치 (마지막에 그려서 맨 위에 표시) -->
     <MyTankIcon
      :x="coordToSvg(current.x, current.y).x"
      :y="coordToSvg(current.x, current.y).y"
      :size="14"
    />
  </svg>
</template>

<style scoped>
svg {
  display: block;
  margin: 0 auto;
}
</style>