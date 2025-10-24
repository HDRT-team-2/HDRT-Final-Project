<script setup lang="ts">
import BaseTable from '@/components/common/BaseTable.vue';
import { computed } from 'vue';

interface FireScheduleItem {
  id: number;
  target: string;
  priority: number;
  fireTime: string;
  hitStatus: 'hit' | 'miss' | 'pending' | 'firing';
  coordinates: { x: number; y: number };
}

const props = defineProps<{
  schedules: FireScheduleItem[];
}>();

const columns = [
  { key: 'priority', label: '순위', align: 'center' as const, width: '50px' },
  { key: 'targetWithCoords', label: '목표 [좌표]', align: 'left' as const },
  { key: 'fireTime', label: '발포시간', align: 'center' as const, width: '70px' },
  { key: 'hitStatus', label: '적중', align: 'center' as const, width: '70px' }
];

const getHitStatusColor = (hitStatus: string) => {
  switch (hitStatus) {
    case 'hit': return 'text-green-600 bg-green-100';
    case 'miss': return 'text-red-600 bg-red-100';
    case 'firing': return 'text-orange-600 bg-orange-100';
    case 'pending': return 'text-gray-600 bg-gray-100';
    default: return 'text-gray-600 bg-gray-100';
  }
};

const getHitStatusText = (hitStatus: string) => {
  switch (hitStatus) {
    case 'hit': return '적중';
    case 'miss': return '빗나감';
    case 'firing': return '발사중';
    case 'pending': return '대기';
    default: return hitStatus;
  }
};
</script>

<template>
  <BaseTable 
    :columns="columns" 
    :data="schedules"
    :striped="true"
    :bordered="true"
    :hover="true"
    size="sm"
  >
    <!-- 우선순위 컬럼 -->
    <template #priority="{ value }">
      <span class="font-semibold text-primary-600">{{ value }}</span>
    </template>
    
    <!-- 목표와 좌표 합친 컬럼 -->
    <template #targetWithCoords="{ row }">
      <span>
        {{ row.target }}
        <span class="font-mono text-xs text-gray-600">
          [{{ String(row.coordinates.x).padStart(3, '0') }}, {{ String(row.coordinates.y).padStart(3, '0') }}]
        </span>
      </span>
    </template>
    
    <!-- 발포시간 컬럼 -->
    <template #fireTime="{ value }">
      <span class="font-mono text-xs">{{ value }}</span>
    </template>
    
    <!-- 적중 상태 컬럼 -->
    <template #hitStatus="{ value }">
      <span 
        class="px-2 py-1 rounded-full text-xs font-medium"
        :class="getHitStatusColor(value)"
      >
        {{ getHitStatusText(value) }}
      </span>
    </template>
    
    <!-- 빈 상태 -->
    <template #empty>
      <div class="text-gray-500">
        발포 기록이 없습니다.
      </div>
    </template>
  </BaseTable>
</template>