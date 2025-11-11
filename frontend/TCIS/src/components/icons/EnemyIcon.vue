<script setup lang="ts">
interface Props {
  x: number
  y: number
  size?: number
}

const props = withDefaults(defineProps<Props>(), {
  size: 10
})

// 핀 비율 (원본 SVG 기준: 17x19)
const scale = props.size / 10
const pinWidth = 17 * scale
const pinHeight = 19 * scale
const color = '#FF0000' // 기본 색상 설정

// 중심점 기준으로 offset 계산
const offsetX = props.x - pinWidth / 2
const offsetY = props.y - pinHeight / 2
</script>

<template>
  <g :transform="`translate(${offsetX}, ${offsetY})`">
    <!-- 회전된 사각형 (다이아몬드) -->
    <rect
      :x="0.707107 * scale"
      :y="10.5 * scale"
      :width="11.0208 * scale"
      :height="11.0208 * scale"
      rx="0.5"
      :transform="`rotate(-45 ${0.707107 * scale} ${10.5 * scale})`"
      :stroke="color"
      fill="none"
      :stroke-width="1 * scale"
    />
    
    <!-- 타원 -->
    <path
      :d="`M ${8.5 * scale} ${8.5 * scale} C ${9.52585 * scale} ${8.5 * scale} ${10.4309 * scale} ${8.76089 * scale} ${11.0635 * scale} ${9.15625 * scale} C ${11.7031 * scale} ${9.55601 * scale} ${12 * scale} ${10.0443 * scale} ${12 * scale} ${10.5 * scale} C ${12 * scale} ${10.9557 * scale} ${11.7031 * scale} ${11.444 * scale} ${11.0635 * scale} ${11.8438 * scale} C ${10.4309 * scale} ${12.2391 * scale} ${9.52585 * scale} ${12.5 * scale} ${8.5 * scale} ${12.5 * scale} C ${7.47415 * scale} ${12.5 * scale} ${6.56909 * scale} ${12.2391 * scale} ${5.93652 * scale} ${11.8438 * scale} C ${5.29693 * scale} ${11.444 * scale} ${5 * scale} ${10.9557 * scale} ${5 * scale} ${10.5 * scale} C ${5 * scale} ${10.0443 * scale} ${5.29693 * scale} ${9.55601 * scale} ${5.93652 * scale} ${9.15625 * scale} C ${6.56909 * scale} ${8.76089 * scale} ${7.47415 * scale} ${8.5 * scale} ${8.5 * scale} ${8.5 * scale} Z`"
      :stroke="color"
      fill="none"
      :stroke-width="1 * scale"
    />
    
    <!-- 상단 원 -->
    <circle
      :cx="8.5 * scale"
      :cy="1 * scale"
      :r="1 * scale"
      :fill="color"
    />
  </g>
</template>