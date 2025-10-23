<script setup lang="ts">
import Card from '@/components/common/Card.vue';
import SituationLogItem from '@/components/common/SituationLogItem.vue';
import { ref, computed } from 'vue';

interface SituationEvent {
  id: number;
  type: 'enemy_detected' | 'ally_detected' | 'enemy_attack';
  time: string;
  target: string;
  coordinates?: { x: number; y: number };
}

// 샘플 데이터 (실제로는 store나 props에서 받아올 예정)
const events = ref<SituationEvent[]>([
  { id: 1, type: 'enemy_detected', time: '14:30', target: '적군 탱크', coordinates: { x: 120, y: 340 } },
  { id: 2, type: 'ally_detected', time: '14:25', target: '아군 헬기', coordinates: { x: 520, y: 440 } },
  { id: 3, type: 'enemy_attack', time: '14:35', target: '적군 보병' },
  { id: 4, type: 'enemy_detected', time: '14:40', target: '적군 장갑차', coordinates: { x: 220, y: 140 } },
  { id: 5, type: 'enemy_detected', time: '14:45', target: '적군 레이더', coordinates: { x: 450, y: 320 } },
]);

// 최신순으로 정렬
const sortedEvents = computed(() => {
  return [...events.value].sort((a, b) => b.time.localeCompare(a.time));
});
</script>

<template>
  <Card title="상황인지 결과">
    <div class="h-full flex flex-col">
      <div class="flex-1 overflow-y-auto space-y-1">
        <SituationLogItem 
          v-for="event in sortedEvents" 
          :key="event.id"
          :event="event"
        />
        
        <!-- 빈 상태 -->
        <div v-if="events.length === 0" class="text-center py-4 text-gray-500 text-xs">
          상황인지 결과가 없습니다.
        </div>
      </div>
    </div>
  </Card>
</template>