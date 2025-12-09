<script setup lang="ts">
interface Props {
  x: number
  y: number
  size?: number
}

const props = withDefaults(defineProps<Props>(), {
  size: 10
})

// 아이콘 비율 (원본 SVG 기준: 32x32)
const scale = props.size / 10
const backgroundRadius = 40 * scale
const centerRadius = 4 * scale
const color = '#FF0000'
</script>

<template>
  <g>
    <!-- 배경 원 (투명도) -->
    <circle
      :cx="props.x"
      :cy="props.y"
      :r="backgroundRadius"
      :fill="color"
      fill-opacity="0.15"
    />
    
    <!-- 중심 원 -->
    <circle
      :cx="props.x"
      :cy="props.y"
      :r="centerRadius"
      :fill="color"
    />
  </g>
</template>
