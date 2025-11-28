<script setup lang="ts">
import type { DetectedObject } from '@/types/detection'
import EnemyIcon from '@/components/icons/EnemyIcon.vue'
import CarIcon from '@/components/icons/CarIcon.vue'
import PersonIcon from '@/components/icons/PersonIcon.vue'
import RockIcon from '@/components/icons/RockIcon.vue'
import MineIcon from '@/components/icons/MineIcon.vue'

interface Props {
  objects: DetectedObject[]
  coordToSvg: (x: number, y: number) => { x: number; y: number }
}

defineProps<Props>()
</script>

<template>
  <!-- 탐지된 객체들 -->
  <g v-for="obj in objects" :key="obj.tracking_id">
    <!-- 적 전차 -->
    <EnemyIcon 
      v-if="obj.class_name === 'tank'"
      :x="coordToSvg(obj.position.x, obj.position.y).x"
      :y="coordToSvg(obj.position.x, obj.position.y).y"
      :size="20"
    />

    <!-- 적 보병 -->
    <PersonIcon 
      v-else-if="obj.class_name === 'human'"
      :x="coordToSvg(obj.position.x, obj.position.y).x"
      :y="coordToSvg(obj.position.x, obj.position.y).y"
      :size="8"
    />
    
    <!-- 차량 -->
    <CarIcon 
      v-else-if="obj.class_name === 'car' || obj.class_name === 'truck'"
      :x="coordToSvg(obj.position.x, obj.position.y).x"
      :y="coordToSvg(obj.position.x, obj.position.y).y"
      :size="10"
    />

    <!-- 작은 바위 -->
    <RockIcon 
      v-else-if="obj.class_name === 'rock_small'"
      :x="coordToSvg(obj.position.x, obj.position.y).x"
      :y="coordToSvg(obj.position.x, obj.position.y).y"
      :size="8"
    />

    <!-- 큰 바위 -->
    <RockIcon 
      v-else-if="obj.class_name === 'rock_large'"
      :x="coordToSvg(obj.position.x, obj.position.y).x"
      :y="coordToSvg(obj.position.x, obj.position.y).y"
      :size="20"
    />
    
    <!-- 지뢰 -->
    <MineIcon 
      v-else-if="obj.class_name === 'mine'"
      :x="coordToSvg(obj.position.x, obj.position.y).x"
      :y="coordToSvg(obj.position.x, obj.position.y).y"
      :size="14"
    />
  </g>
</template>
