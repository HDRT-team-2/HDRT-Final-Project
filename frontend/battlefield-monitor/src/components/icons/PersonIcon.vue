<script setup lang="ts">
interface Props {
  x: number
  y: number
  size?: number
}

const props = withDefaults(defineProps<Props>(), {
  size: 8
})

// 사람 모양 비율
const headRadius = size * 0.3
const bodyHeight = size * 0.8
const bodyWidth = size * 0.4
</script>

<template>
  <g>
    <!-- 머리 -->
    <circle 
      :cx="x"
      :cy="y - size * 0.4"
      :r="headRadius"
      fill="#22c55e"
      stroke="#fff"
      stroke-width="1"
    />
    <!-- 몸통 -->
    <rect
      :x="x - bodyWidth / 2"
      :y="y - size * 0.1"
      :width="bodyWidth"
      :height="bodyHeight"
      fill="#22c55e"
      stroke="#fff"
      stroke-width="1"
      rx="2"
    />
  </g>
</template>