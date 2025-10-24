<script setup lang="ts">
import Card from '@/components/common/Card.vue';
import FireScheduleTable from '@/components/sidebar/FireScheduleTable.vue';

// 샘플 데이터
const schedules = [
  {
    id: 1,
    target: '적군 탱크',
    priority: 1,
    fireTime: '14:30',
    hitStatus: 'hit' as const,
    coordinates: { x: 120, y: 340 }
  },
  {
    id: 2,
    target: '적군 보병',
    priority: 2,
    fireTime: '14:32',
    hitStatus: 'miss' as const,
    coordinates: { x: 220, y: 140 }
  },
  {
    id: 3,
    target: '적군 거점',
    priority: 3,
    fireTime: '14:35',
    hitStatus: 'firing' as const,
    coordinates: { x: 320, y: 240 }
  },
];
</script>
<template>
  <Card title="타격 스케줄링">
    <!-- 스케줄 테이블 -->
    <FireScheduleTable :schedules="schedules" />
  </Card>
</template>