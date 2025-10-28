<script setup lang="ts">
import BaseTable from '@/components/common/BaseTable.vue';

interface FireScheduleItem {
  id: string;
  target_tracking_id: number;
  firedAt: Date;
  hitStatus: 'hit' | 'miss' | 'pending';
}

const props = defineProps<{
  schedules: FireScheduleItem[];
}>();

const columns = [
  { key: 'target_tracking_id', label: '대상 ID', align: 'center' as const, width: '80px' },
  { key: 'fireTime', label: '발포시간', align: 'center' as const, width: '100px' },
  { key: 'hitStatus', label: '적중', align: 'center' as const, width: '80px' }
];

const getHitStatusColor = (hitStatus: string) => {
  switch (hitStatus) {
    case 'hit': return 'text-green-600 bg-green-100';
    case 'miss': return 'text-red-600 bg-red-100';
    case 'pending': return 'text-orange-600 bg-orange-100';
    default: return 'text-gray-600 bg-gray-100';
  }
};

const getHitStatusText = (hitStatus: string) => {
  switch (hitStatus) {
    case 'hit': return '적중';
    case 'miss': return '빗나감';
    case 'pending': return '대기중';
    default: return hitStatus;
  }
};

// 시간 포맷 (HH:MM:SS)
const formatTime = (date: Date) => {
  return date.toLocaleTimeString('ko-KR', { 
    hour: '2-digit', 
    minute: '2-digit',
    second: '2-digit'
  });
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
    <!-- 대상 ID 컬럼 -->
    <template #target_tracking_id="{ value }">
      <span class="font-mono font-semibold">{{ value }}</span>
    </template>
    
    <!-- 발포시간 컬럼 -->
    <template #fireTime="{ row }">
      <span class="font-mono text-xs">{{ formatTime(row.firedAt) }}</span>
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