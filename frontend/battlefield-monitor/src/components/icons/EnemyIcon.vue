<script setup lang="ts">
interface Props {
  x: number
  y: number
  size?: number
}

const props = withDefaults(defineProps<Props>(), {
  size: 10
})
</script>

<template>
  <g>
    <!-- 외곽선 -->
    <circle 
      :cx="props.x"
      :cy="props.y"
      :r="props.size"
      fill="#dc2626"
      stroke="#fff"
      stroke-width="2"
    />
    <!-- 중앙점 -->
    <circle 
      :cx="props.x"
      :cy="props.y"
      :r="props.size * 0.3"
      fill="#7f1d1d"
    />
    <!-- <text 
      :x="props.x + props.size + 4"
      :y="props.y + 4"
      font-size="10"
      fill="#dc2626"
      font-weight="bold"
    >
      적군
    </text> -->
  </g>
</template>