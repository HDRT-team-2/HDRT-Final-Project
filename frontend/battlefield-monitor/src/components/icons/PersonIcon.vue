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
const headRadius = props.size * 0.3
const bodyHeight = props.size * 0.8
const bodyWidth = props.size * 0.4
</script>

<template>
  <g>
    <!-- 머리 -->
    <circle 
      :cx="props.x"
      :cy="props.y - props.size * 0.4"
      :r="headRadius"
      fill="#22c55e"
      stroke="#fff"
      stroke-width="1"
    />
    <!-- 몸통 -->
    <rect
      :x="props.x - bodyWidth / 2"
      :y="props.y - props.size * 0.1"
      :width="bodyWidth"
      :height="bodyHeight"
      fill="#22c55e"
      stroke="#fff"
      stroke-width="1"
      rx="2"
    />
    <!-- <text
      :x="props.x + props.size * 0.6"
      :y="props.y + bodyHeight / 2"
      font-size="10"
      fill="#22c55e"
      font-weight="bold"
    >
      민간인
    </text> -->
  </g>
</template>