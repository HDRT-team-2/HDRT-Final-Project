<script setup lang="ts">
interface Props {
  x: number
  y: number
  size?: number
}

const props = withDefaults(defineProps<Props>(), {
  size: 10
})

// 마름모 비율 (원본 SVG 기준: 19x19)
const scale = props.size / 10
const diamondSize = 19 * scale
const color = '#919AB7' // 기본 색상 설정

// 중심점 기준으로 offset 계산
const offsetX = props.x - diamondSize / 2
const offsetY = props.y - diamondSize / 2
</script>

<template>
  <g :transform="`translate(${offsetX}, ${offsetY})`">
    <!-- 마름모 -->
    <path
      :d="`M 0 ${9.19239 * scale} L ${9.19239 * scale} 0 L ${18.3848 * scale} ${9.19239 * scale} L ${9.19239 * scale} ${18.3848 * scale} L 0 ${9.19239 * scale} Z`"
      :fill="color"
    />
  </g>
</template>