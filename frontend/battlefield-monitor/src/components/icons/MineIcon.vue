<script setup lang="ts">
interface Props {
  x: number
  y: number
  size?: number
}

const props = withDefaults(defineProps<Props>(), {
  size: 12
})

// 다이아몬드 비율 (원본 SVG 기준: 15x15)
const scale = props.size / 12
const color = '#FF0000' // 기본 색상 설정
</script>

<template>
  <g>
    <!-- 위쪽 삼각형 -->
    <path
      :d="`M ${props.x - 0.86603 * scale} ${props.y - 6 * scale}
           C ${props.x - 0.48113 * scale} ${props.y - 6.66667 * scale}
             ${props.x + 0.48113 * scale} ${props.y - 6.66667 * scale}
             ${props.x + 0.86603 * scale} ${props.y - 6 * scale}
           L ${props.x + 5.62918 * scale} ${props.y + 2.25 * scale}
           C ${props.x + 6.01408 * scale} ${props.y + 2.91667 * scale}
             ${props.x + 5.53295 * scale} ${props.y + 3.75 * scale}
             ${props.x + 4.76315 * scale} ${props.y + 3.75 * scale}
           H ${props.x - 4.76314 * scale}
           C ${props.x - 5.53294 * scale} ${props.y + 3.75 * scale}
             ${props.x - 6.01407 * scale} ${props.y + 2.91667 * scale}
             ${props.x - 5.62917 * scale} ${props.y + 2.25 * scale}
           L ${props.x - 0.86603 * scale} ${props.y - 6 * scale} Z`"
      :fill="color"
    />
    
    <!-- 아래쪽 삼각형 -->
    <path
      :d="`M ${props.x + 0.86602 * scale} ${props.y + 6 * scale}
           C ${props.x + 0.48112 * scale} ${props.y + 6.66667 * scale}
             ${props.x - 0.48113 * scale} ${props.y + 6.66667 * scale}
             ${props.x - 0.86603 * scale} ${props.y + 6 * scale}
           L ${props.x - 5.62917 * scale} ${props.y - 2.25 * scale}
           C ${props.x - 6.01407 * scale} ${props.y - 2.91667 * scale}
             ${props.x - 5.53294 * scale} ${props.y - 3.75 * scale}
             ${props.x - 4.76314 * scale} ${props.y - 3.75 * scale}
           L ${props.x + 4.76315 * scale} ${props.y - 3.75 * scale}
           C ${props.x + 5.53295 * scale} ${props.y - 3.75 * scale}
             ${props.x + 6.01408 * scale} ${props.y - 2.91667 * scale}
             ${props.x + 5.62918 * scale} ${props.y - 2.25 * scale}
           L ${props.x + 0.86602 * scale} ${props.y + 6 * scale} Z`"
      :fill="color"
    />
  </g>
</template>