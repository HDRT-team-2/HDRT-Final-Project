<script setup lang="ts">
interface Props {
  x: number
  y: number
  size?: number
}

const props = withDefaults(defineProps<Props>(), {
  size: 10
})

// 차 모양 비율
const carWidth = props.size * 1.4
const carHeight = props.size * 0.8
const roofWidth = props.size * 0.8
const roofHeight = props.size * 0.5
</script>

<template>
  <g>
    <!-- 차체 (하단) -->
    <rect
      :x="props.x - carWidth / 2"
      :y="props.y - carHeight / 2"
      :width="carWidth"
      :height="carHeight"
      fill="#22c55e"
      stroke="#fff"
      stroke-width="1.5"
      rx="2"
    />
    <!-- 지붕 (상단) -->
    <rect
      :x="props.x - roofWidth / 2"
      :y="props.y - carHeight / 2 - roofHeight"
      :width="roofWidth"
      :height="roofHeight"
      fill="#16a34a"
      stroke="#fff"
      stroke-width="1.5"
      rx="1"
    />
    <!-- 바퀴 (왼쪽) -->
    <circle
      :cx="props.x - carWidth * 0.3"
      :cy="props.y + carHeight / 2"
      :r="props.size * 0.15"
      fill="#374151"
    />
    <!-- 바퀴 (오른쪽) -->
    <circle
      :cx="props.x + carWidth * 0.3"
      :cy="props.y + carHeight / 2"
      :r="props.size * 0.15"
      fill="#374151"
    />
  </g>
</template>