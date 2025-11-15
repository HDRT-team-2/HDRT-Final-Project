<script setup lang="ts">
interface Props {
  x: number
  y: number
  size?: number
}

const props = withDefaults(defineProps<Props>(), {
  size: 12
})

// 핀 비율 (원본 SVG 기준: 22x15)
const scale = props.size / 12 // size 12를 기준으로
const color = '#31447E' // 기본 색상 설정
</script>

<template>
  <g>
    <!-- 외곽 사각형 -->
    <rect
      :x="props.x - 10.5 * scale"
      :y="props.y - 5.84375 * scale"
      :width="21 * scale"
      :height="11.1875 * scale"
      rx="0.5"
      :stroke="color"
      fill="none"
      :stroke-width="1 * scale"
    />
    
    <!-- 중앙 타원 -->
    <path
      :d="`M ${props.x} ${props.y - 2.78125 * scale} 
           C ${props.x + 1.8765 * scale} ${props.y - 2.78125 * scale} 
             ${props.x + 3.5507 * scale} ${props.y - 2.42339 * scale} 
             ${props.x + 4.7373 * scale} ${props.y - 1.86719 * scale} 
           C ${props.x + 5.9638 * scale} ${props.y - 1.29228 * scale} 
             ${props.x + 6.5 * scale} ${props.y - 0.59762 * scale} 
             ${props.x + 6.5 * scale} ${props.y} 
           C ${props.x + 6.5 * scale} ${props.y + 0.59762 * scale} 
             ${props.x + 5.9638 * scale} ${props.y + 1.29228 * scale} 
             ${props.x + 4.7373 * scale} ${props.y + 1.86719 * scale} 
           C ${props.x + 3.5507 * scale} ${props.y + 2.42339 * scale} 
             ${props.x + 1.8765 * scale} ${props.y + 2.78125 * scale} 
             ${props.x} ${props.y + 2.78125 * scale} 
           C ${props.x - 1.8765 * scale} ${props.y + 2.78125 * scale} 
             ${props.x - 3.5507 * scale} ${props.y + 2.42339 * scale} 
             ${props.x - 4.7373 * scale} ${props.y + 1.86719 * scale} 
           C ${props.x - 5.9638 * scale} ${props.y + 1.29228 * scale} 
             ${props.x - 6.5 * scale} ${props.y + 0.59762 * scale} 
             ${props.x - 6.5 * scale} ${props.y} 
           C ${props.x - 6.5 * scale} ${props.y - 0.59762 * scale} 
             ${props.x - 5.9638 * scale} ${props.y - 1.29228 * scale} 
             ${props.x - 4.7373 * scale} ${props.y - 1.86719 * scale} 
           C ${props.x - 3.5507 * scale} ${props.y - 2.42339 * scale} 
             ${props.x - 1.8765 * scale} ${props.y - 2.78125 * scale} 
             ${props.x} ${props.y - 2.78125 * scale} Z`"
      :stroke="color"
      fill="none"
      :stroke-width="1 * scale"
    />
    
    <!-- 상단 타원 -->
    <ellipse
      :cx="props.x"
      :cy="props.y - 7.96875 * scale"
      :rx="1 * scale"
      :ry="0.9375 * scale"
      :fill="color"
    />
  </g>
</template>