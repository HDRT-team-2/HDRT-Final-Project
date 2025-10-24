<script setup lang="ts">
interface SituationEvent {
  id: number;
  type: 'enemy_detected' | 'ally_detected' | 'enemy_attack';
  time: string;
  target: string;
  coordinates?: { x: number; y: number };
}

const props = defineProps<{
  event: SituationEvent;
}>();

// 이벤트 타입별 스타일 및 텍스트
const getEventStyle = (type: string) => {
  switch (type) {
    case 'enemy_detected':
      return {
        bgColor: 'bg-red-50',
        borderColor: 'border-red-200',
        textColor: 'text-red-700',
        label: '적 탐지'
      };
    case 'ally_detected':
      return {
        bgColor: 'bg-blue-50',
        borderColor: 'border-blue-200', 
        textColor: 'text-blue-700',
        label: '아군 탐지'
      };
    case 'enemy_attack':
      return {
        bgColor: 'bg-orange-50',
        borderColor: 'border-orange-200',
        textColor: 'text-orange-700',
        label: '적 공격'
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
    <!-- 왼쪽: 타입, 대상 -->
    <div class="flex flex-col">
      <span 
        class="text-xs font-semibold"
        :class="getEventStyle(event.type).textColor"
      >
        {{ getEventStyle(event.type).label }}
      </span>
      <span class="text-xs text-gray-600">
        {{ event.target }}
        <span v-if="event.coordinates" class="font-mono">
          [{{ String(event.coordinates.x).padStart(3, '0') }}, {{ String(event.coordinates.y).padStart(3, '0') }}]
        </span>
      </span>
    </div>
    
    <!-- 오른쪽: 시간 -->
    <span 
      class="text-xs font-mono font-semibold"
      :class="getEventStyle(event.type).textColor"
    >
      {{ event.time }}
    </span>
  </div>
</template>