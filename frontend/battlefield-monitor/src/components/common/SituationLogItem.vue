<script setup lang="ts">
import type { SituationEvent } from '@/types/situation';
const props = defineProps<{ event: SituationEvent }>();

// 타입별 스타일 및 라벨
const getEventStyle = (type: SituationEvent['type']) => {
  switch (type) {
    case 'detection':
      return {
        bgColor: 'bg-blue-50',
        borderColor: 'border-blue-200',
        textColor: 'text-blue-700',
        label: '탐지'
      };
    case 'fire':
      return {
        bgColor: 'bg-orange-50',
        borderColor: 'border-orange-200',
        textColor: 'text-orange-700',
        label: '발포'
      };
    default:
      return {
        bgColor: 'bg-gray-50',
        borderColor: 'border-gray-200',
        textColor: 'text-gray-700',
        label: '기타'
      };
  }
};
</script>

<template>
  <div 
    class="flex items-center justify-between p-2 rounded border"
    :class="[
      getEventStyle(event.type).bgColor,
      getEventStyle(event.type).borderColor
    ]"
  >
    <!-- 왼쪽: 타입/메시지 -->
    <div class="flex flex-col">
      <span 
        class="text-xs font-semibold"
        :class="getEventStyle(event.type).textColor"
      >
        {{ getEventStyle(event.type).label }}
      </span>
      <span class="text-xs text-gray-700">
        {{ event.message }}
      </span>
    </div>
    <!-- 오른쪽: 시간 -->
    <span 
      class="text-xs font-mono font-semibold"
      :class="getEventStyle(event.type).textColor"
    >
      {{ typeof event.time === 'string' ? event.time : event.time.toLocaleTimeString('ko-KR', { hour12: false }) }}
    </span>
  </div>
</template>