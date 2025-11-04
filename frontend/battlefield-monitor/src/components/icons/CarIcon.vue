<script setup lang="ts">
interface Props {
  x: number
  y: number
  size?: number
}

const props = withDefaults(defineProps<Props>(), {
  size: 10
})

// 차 모양 비율 (원본 SVG 기준: 20x16)
const scale = props.size / 10 // 기본 크기 10 기준으로 스케일링
const carWidth = 20 * scale
const carHeight = 16 * scale
const color = '#F97316' // 기본 색상 설정

// 중심점 기준으로 offset 계산
const offsetX = props.x - carWidth / 2
const offsetY = props.y - carHeight / 2
</script>

<template>
  <g :transform="`translate(${offsetX}, ${offsetY})`">
    <!-- 차체 하단 -->
    <path
      :d="`M 0 ${8 * scale} C 0 ${6.895 * scale} ${0.895 * scale} ${6 * scale} ${2 * scale} ${6 * scale} H ${18 * scale} C ${19.105 * scale} ${6 * scale} ${20 * scale} ${6.895 * scale} ${20 * scale} ${8 * scale} V ${13 * scale} H 0 V ${8 * scale} Z`"
      :fill="color"
    />
    
    <!-- 차체 상단 (지붕) -->
    <path
      :d="`M ${3 * scale} ${3 * scale} C ${3 * scale} ${1.343 * scale} ${4.343 * scale} 0 ${6 * scale} 0 H ${14 * scale} C ${15.657 * scale} 0 ${17 * scale} ${1.343 * scale} ${17 * scale} ${3 * scale} V ${6 * scale} H ${3 * scale} V ${3 * scale} Z`"
      :fill="color"
    />
    
    <!-- 바퀴 왼쪽 -->
    <circle
      :cx="5 * scale"
      :cy="12 * scale"
      :r="3.5 * scale"
      :fill="color"
      stroke="#F7F7F9"
      :stroke-width="1 * scale"
    />
    
    <!-- 바퀴 오른쪽 -->
    <circle
      :cx="15 * scale"
      :cy="12 * scale"
      :r="3.5 * scale"
      :fill="color"
      stroke="#F7F7F9"
      :stroke-width="1 * scale"
    />
  </g>
</template>