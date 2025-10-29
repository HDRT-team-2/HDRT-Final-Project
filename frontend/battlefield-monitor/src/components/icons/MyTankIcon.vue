<script setup lang="ts">
interface Props {
  x: number
  y: number
  size?: number
}

const props = withDefaults(defineProps<Props>(), {
  size: 12
})
</script>

<template>
  <g>
    <!-- 외곽선 -->
    <circle 
      :cx="props.x"
      :cy="props.y"
      :r="props.size"
      fill="#3b82f6"
      stroke="#fff"
      stroke-width="2"
    />
    <!-- 중앙점 -->
    <circle 
      :cx="props.x"
      :cy="props.y"
      :r="props.size * 0.3"
      fill="#1e40af"
    />
    <!-- <text 
      :x="props.x + props.size + 4"
      :y="props.y + 4"
      font-size="12"
      fill="#1e40af"
      font-weight="bold"
    >
      아군
    </text> -->
  </g>
</template>