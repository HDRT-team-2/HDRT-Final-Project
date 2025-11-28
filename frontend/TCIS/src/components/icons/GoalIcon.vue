<script setup lang="ts">
interface Props {
  x: number
  y: number
  size?: number
  isDanger?: boolean // true면 빨강, false면 초록
}

const props = withDefaults(defineProps<Props>(), {
  size: 12,
  isDanger: false
})

// 원본 SVG 기준: 12x12
const radius = props.size / 2
const innerRadius = radius * 0.4 // 2.4 / 6 비율
const color = props.isDanger ? '#CC0000' : '#15803D'
</script>

<template>
  <g>
    <!-- 내부 원 (채워진) -->
    <circle
      :cx="props.x"
      :cy="props.y"
      :r="innerRadius"
      :fill="color"
    />
    
    <!-- 외부 원 (테두리만) -->
    <circle
      :cx="props.x"
      :cy="props.y"
      :r="radius - 0.5"
      :stroke="color"
      stroke-width="1"
      fill="none"
    />
  </g>
</template>