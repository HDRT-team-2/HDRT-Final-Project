<script setup lang="ts">
interface Props {
  x: number
  y: number
  size?: number
}

const props = withDefaults(defineProps<Props>(), {
  size: 10
})

// 원본 SVG는 48x48, 중심이 24,24
// size 10을 기준으로 스케일 조정
const scale = props.size / 10
const backgroundRadius = 24 * scale / 2.4  // 배경 원을 적절히 축소
const color = '#FF0000'

// 원본 SVG의 중심이 (24, 24)이므로, props.x, props.y를 중심으로 재배치
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
    
    <!-- 회전된 사각형 (다이아몬드) - 원본 SVG: x=16.7071, y=25.5, center=(24,24) -->
    <rect
      :x="(props.x - (24 - 16.7071) * scale / 2.4)"
      :y="(props.y + (25.5 - 24) * scale / 2.4)"
      :width="11.0208 * scale / 2.4"
      :height="11.0208 * scale / 2.4"
      rx="0.5"
      :transform="`rotate(-45 ${props.x - (24 - 16.7071) * scale / 2.4} ${props.y + (25.5 - 24) * scale / 2.4})`"
      :stroke="color"
      fill="none"
      :stroke-width="1 * scale / 2.4"
    />
    
    <!-- 타원 - 원본 SVG: 중심이 약 (24.5, 25.5) -> 중앙(24)으로 조정 -->
    <path
      :d="`M ${props.x + 0.5 * scale / 2.4} ${props.y - 0.5 * scale / 2.4} 
           C ${props.x + 1.5259 * scale / 2.4} ${props.y - 0.5 * scale / 2.4} ${props.x + 2.4309 * scale / 2.4} ${props.y - 0.2391 * scale / 2.4} ${props.x + 3.0635 * scale / 2.4} ${props.y + 0.1562 * scale / 2.4} 
           C ${props.x + 3.7031 * scale / 2.4} ${props.y + 0.556 * scale / 2.4} ${props.x + 4 * scale / 2.4} ${props.y + 1.0443 * scale / 2.4} ${props.x + 4 * scale / 2.4} ${props.y + 1.5 * scale / 2.4} 
           C ${props.x + 4 * scale / 2.4} ${props.y + 1.9557 * scale / 2.4} ${props.x + 3.7031 * scale / 2.4} ${props.y + 2.444 * scale / 2.4} ${props.x + 3.0635 * scale / 2.4} ${props.y + 2.8438 * scale / 2.4} 
           C ${props.x + 2.4309 * scale / 2.4} ${props.y + 3.2391 * scale / 2.4} ${props.x + 1.5259 * scale / 2.4} ${props.y + 3.5 * scale / 2.4} ${props.x + 0.5 * scale / 2.4} ${props.y + 3.5 * scale / 2.4} 
           C ${props.x - 0.5259 * scale / 2.4} ${props.y + 3.5 * scale / 2.4} ${props.x - 1.4309 * scale / 2.4} ${props.y + 3.2391 * scale / 2.4} ${props.x - 2.0635 * scale / 2.4} ${props.y + 2.8438 * scale / 2.4} 
           C ${props.x - 2.7031 * scale / 2.4} ${props.y + 2.444 * scale / 2.4} ${props.x - 3 * scale / 2.4} ${props.y + 1.9557 * scale / 2.4} ${props.x - 3 * scale / 2.4} ${props.y + 1.5 * scale / 2.4} 
           C ${props.x - 3 * scale / 2.4} ${props.y + 1.0443 * scale / 2.4} ${props.x - 2.7031 * scale / 2.4} ${props.y + 0.556 * scale / 2.4} ${props.x - 2.0635 * scale / 2.4} ${props.y + 0.1562 * scale / 2.4} 
           C ${props.x - 1.4309 * scale / 2.4} ${props.y - 0.2391 * scale / 2.4} ${props.x - 0.5259 * scale / 2.4} ${props.y - 0.5 * scale / 2.4} ${props.x + 0.5 * scale / 2.4} ${props.y - 0.5 * scale / 2.4} Z`"
      :stroke="color"
      fill="none"
      :stroke-width="1 * scale / 2.4"
    />
    
    <!-- 상단 원 - 원본 SVG: cx=24.5, cy=16, center=(24,24) -->
    <circle
      :cx="props.x + 0.5 * scale / 2.4"
      :cy="props.y - 8 * scale / 2.4"
      :r="1 * scale / 2.4"
      :fill="color"
    />
  </g>
</template>
