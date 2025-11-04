<script setup lang="ts">
interface Props {
  x: number
  y: number
  size?: number
}

const props = withDefaults(defineProps<Props>(), {
  size: 10
})

// 화살표 비율 (원본 SVG 기준: 13x17)
const scale = props.size / 10
const arrowWidth = 13 * scale
const arrowHeight = 17 * scale
const color = '#0A2369'

// 중심점을 (0,0)으로 맞추기 위한 offset
const centerOffsetX = -arrowWidth / 2
const centerOffsetY = -arrowHeight / 2
</script>

<template>
  <g>
    <!-- 화살표 몸통 (세로 막대) -->
    <rect
      :x="props.x + centerOffsetX + 3 * scale"
      :y="props.y + centerOffsetY"
      :width="1 * scale"
      :height="17 * scale"
      :fill="color"
    />
    
    <!-- 화살표 머리 (삼각형) -->
    <path
      :d="`M ${props.x + centerOffsetX + 13 * scale} ${props.y + centerOffsetY + 3.5 * scale} L ${props.x + centerOffsetX + 3.25 * scale} ${props.y + centerOffsetY + 6.53109 * scale} V ${props.y + centerOffsetY + 0.468911 * scale} L ${props.x + centerOffsetX + 13 * scale} ${props.y + centerOffsetY + 3.5 * scale} Z`"
      :fill="color"
    />
  </g>
</template>