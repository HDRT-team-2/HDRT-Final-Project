<script setup lang="ts">
interface Props {
  x: number
  y: number
  size?: number
}

const props = withDefaults(defineProps<Props>(), {
  size: 10
})

// 원 비율 (원본 SVG 기준: 8x8)
const scale = props.size / 10
const radius = 4 * scale
const color = '#FF0000' // 기본 색상 설정
</script>

<template>
  <g>
    <!-- 빨간 원 -->
    <circle
      :cx="props.x"
      :cy="props.y"
      :r="radius"
      :fill="color"
    />
  </g>
</template>