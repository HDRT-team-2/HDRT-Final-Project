<script setup lang="ts">
import type { SituationEvent } from '@/types/situation'
import Badge from '@/components/common/Badge.vue'
import { CLASS_NAME_KR } from '@/types/detection'
import { computed } from 'vue'

const props = defineProps<{ event: SituationEvent }>()

// 카테고리 결정 (적/아군/기타) - fire도 className 기반으로 분류
const category = computed<'enemy' | 'ally' | 'other'>(() => {
  const className = props.event.className
  if (className === 'tank' || className === 'human') return 'enemy'
  // 아군은 추후 추가 (현재는 없음)
  // if (className === 'ally_tank' || className === 'ally_human') return 'ally'
  return 'other' // car, truck, rock_small, rock_large 등
})

// 카테고리별 스타일
const categoryStyle = computed(() => {
  if (props.event.type === 'fire') {
    return {
      bgColor: 'bg-warning-50',
      borderColor: 'border-warning-200',
      textColor: 'text-warning-600'
    }
  }
  
  switch (category.value) {
    case 'enemy':
      return {
        bgColor: 'bg-danger-50',
        borderColor: 'border-danger-200',
        textColor: 'text-danger-500'
      }
    case 'ally':
      return {
        bgColor: 'bg-rotem-50',
        borderColor: 'border-rotem-200',
        textColor: 'text-rotem-600'
      }
    default: // other
      return {
        bgColor: 'bg-success-50',
        borderColor: 'border-success-200',
        textColor: 'text-success-600'
      }
  }
})

// 배지 텍스트
const badgeText = computed(() => {
  return props.event.type === 'detection' ? '탐지' : '발포'
})

// 배지 색상 (카테고리에 따라 변경)
const badgeColor = computed<'rotem' | 'yellow' | 'danger' | 'success' | 'gray'>(() => {
  if (props.event.type === 'fire') return 'yellow' // 발포: 주황(yellow)
  
  // 탐지인 경우 카테고리별 색상
  switch (category.value) {
    case 'enemy':
      return 'danger' // 적 탐지: 빨강
    case 'ally':
      return 'rotem' // 아군 탐지: 파랑
    default: // other
      return 'success' // 기타 탐지: 초록
  }
})

// 객체 텍스트
const objectText = computed(() => {
  const className = props.event.className
  if (!className) return '알 수 없음'
  
  // 적/아군 접두사 추가
  const prefix = category.value === 'enemy' ? '적 ' : 
                 category.value === 'ally' ? '아군 ' : ''
  
  const koreanName = CLASS_NAME_KR[className as keyof typeof CLASS_NAME_KR] || className
  const objectName = prefix + koreanName
  
  return objectName
})

// 위치 텍스트
const positionText = computed(() => {
  if (!props.event.pos) return ''
  return `[${props.event.pos.x.toFixed(1)}, ${props.event.pos.y.toFixed(1)}]`
})

// 시간 텍스트
const timeText = computed(() => {
  if (!props.event.time) return ''
  return props.event.time.toLocaleTimeString('ko-KR', { 
    hour: '2-digit', 
    minute: '2-digit',
    second: '2-digit',
    hour12: false 
  })
})
</script>

<template>
  <div 
    class="flex items-center gap-2 p-2 rounded border text-xs shadow-md rounded-lg"
    :class="[
      categoryStyle.bgColor,
      categoryStyle.borderColor
    ]"
  >
    <!-- 배지 -->
    <Badge :text="badgeText" :color="badgeColor" />
    
    <!-- 객체 -->
    <span class="font-bold text-xs">
      {{ objectText }}
    </span>
    
    <!-- 위치 -->
    <span class="text-xs">
      {{ positionText }}
    </span>
    
    <!-- 시간 (우측 정렬) -->
    <span class="ml-auto text-xs" :class="categoryStyle.textColor">
      {{ timeText }}
    </span>
  </div>
</template>