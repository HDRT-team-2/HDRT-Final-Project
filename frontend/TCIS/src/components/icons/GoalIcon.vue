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
</script>

<template>
  <g>
    <!-- 빛나는 효과를 위한 외부 원 (애니메이션) -->
    <circle
      :cx="props.x"
      :cy="props.y"
      :r="radius * 1.5"
      :fill="props.isDanger ? '#CC0000' : '#15803D'"
      opacity="0.3"
    >
      <animate
        attributeName="r"
        :from="radius"
        :to="radius * 2"
        dur="1.5s"
        repeatCount="indefinite"
      />
      <animate
        attributeName="opacity"
        from="0.6"
        to="0"
        dur="1.5s"
        repeatCount="indefinite"
      />
    </circle>
    
    <!-- 내부 원 (채워진, 펄스 효과) -->
    <circle
      :cx="props.x"
      :cy="props.y"
      :r="innerRadius"
      :fill="props.isDanger ? '#CC0000' : '#15803D'"
    >
      <animate
        attributeName="opacity"
        values="1;0.5;1"
        dur="1s"
        repeatCount="indefinite"
      />
    </circle>
    
    <!-- 외부 원 (테두리만) -->
    <circle
      :cx="props.x"
      :cy="props.y"
      :r="radius - 0.5"
      :stroke="props.isDanger ? '#CC0000' : '#15803D'"
      stroke-width="1.5"
      fill="none"
    >
      <animate
        attributeName="stroke-width"
        values="1.5;2.5;1.5"
        dur="1s"
        repeatCount="indefinite"
      />
    </circle>
  </g>
</template>