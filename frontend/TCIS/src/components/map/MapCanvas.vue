<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import type { TankPosition, TargetPosition } from '@/types/position'
import type { DetectedObject } from '@/types/detection'
import { useMapStore } from '@/stores/map-store'

import MyTankIcon from '@/components/icons/MyTankIcon.vue'
import GoalIcon from '@/components/icons/GoalIcon.vue'
import EnemyIcon from '@/components/icons/EnemyIcon.vue'
import CarIcon from '@/components/icons/CarIcon.vue'
import PersonIcon from '@/components/icons/PersonIcon.vue'
import RockIcon from '../icons/RockIcon.vue'
import MineIcon from '../icons/MineIcon.vue'

const mapStore = useMapStore()
const { currentMapImage } = storeToRefs(mapStore)

interface Props {
  current: TankPosition    // 내 위치
  target: TargetPosition | null  // 목표 위치
  objects: DetectedObject[]      // 탐지된 객체들
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

</script>

<template>
  <svg 
    :width="canvasWidth" 
    :height="canvasHeight"
    class="border-2 border-gray-400"
    :viewBox="`0 0 ${canvasWidth} ${canvasHeight}`"
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
    
    <!-- 목표 위치 (있으면) -->
     <GoalIcon
      v-if="target"
      :x="coordToSvg(target.x, target.y).x"
      :y="coordToSvg(target.x, target.y).y"
      :size="8"
    />
    
    <!-- 탐지된 객체들 -->
    <g v-for="obj in objects" :key="obj.tracking_id">
      <!-- 적 전차 (사각형) -->
       <EnemyIcon 
        v-if="obj.class_name === 'tank'"
        :x="coordToSvg(obj.position.x, obj.position.y).x"
        :y="coordToSvg(obj.position.x, obj.position.y).y"
        :size="20"
      />

      <!-- 적 보병 (원) -->
       <PersonIcon 
        v-else-if="obj.class_name === 'human'"
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

      <RockIcon 
        v-else-if="obj.class_name === 'rock_small'"
        :x="coordToSvg(obj.position.x, obj.position.y).x"
        :y="coordToSvg(obj.position.x, obj.position.y).y"
        :size="8"
      />

      <RockIcon 
        v-else-if="obj.class_name === 'rock_large'"
        :x="coordToSvg(obj.position.x, obj.position.y).x"
        :y="coordToSvg(obj.position.x, obj.position.y).y"
        :size="20"
      />
      
      <MineIcon 
        v-else-if="obj.class_name === 'mine'"
        :x="coordToSvg(obj.position.x, obj.position.y).x"
        :y="coordToSvg(obj.position.x, obj.position.y).y"
        :size="14"
      />
    </g>
    
    <!-- 내 전차 위치 (마지막에 그려서 맨 위에 표시) -->
     <MyTankIcon
      :x="coordToSvg(current.x, current.y).x"
      :y="coordToSvg(current.x, current.y).y"
      :size="18"
    />
  </svg>
</template>

<style scoped>
svg {
  display: block;
  margin: 0 auto;
}
</style>