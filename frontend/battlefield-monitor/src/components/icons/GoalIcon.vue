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
        fill="none"
        stroke="#10b981"
        stroke-width="3"
        opacity="0.8"
    />
    <!-- 중앙점 -->
    <circle 
      :cx="props.x"
      :cy="props.y"
      :r="props.size * 0.3"
      fill="#10b981"
    />
    <!-- <text 
      :x="props.x + props.size + 4"
      :y="props.y + 4"
      font-size="11"
      fill="#10b981"
      font-weight="bold"
    >
      목표
    </text> -->
  </g>
</template>