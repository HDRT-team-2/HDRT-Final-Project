<script setup lang="ts">
import Card from '@/components/common/Card.vue';
import ObjectsList from '@/components/common/ObjectsList.vue';

const enemies = [
  { id: 1, name: '적군 1', type: '탱크', x: 120, y: 340 },
  { id: 2, name: '적군 2', type: '보병', x: 220, y: 140 },
];

const allies = [
  { id: 1, name: '아군 1', type: '헬기', x: 520, y: 440 },
  { id: 2, name: '아군 2', type: '보병', x: 620, y: 540 },
];

</script>
<template>
  <Card title="탐지 객체">
    <div class="flex flex-col gap-3">
      <!-- 탐지 객체 개수 표시 -->
      <div class="text-center text-sm text-gray-600">
        적군: <span class="font-semibold text-red-600">{{ enemies.length }}</span> | 
        아군: <span class="font-semibold text-blue-600">{{ allies.length }}</span>
      </div>
      
      <!-- 수평으로 배치된 ObjectsList -->
      <div class="flex gap-4">
        <div class="flex-1">
          <h4 class="text-xs font-medium text-red-600 mb-1 text-center">적군</h4>
          <ObjectsList :itemList="enemies" />
        </div>
        <div class="flex-1">
          <h4 class="text-xs font-medium text-blue-600 mb-1 text-center">아군</h4>
          <ObjectsList :itemList="allies" />
        </div>
      </div>
    </div>
  </Card>
</template>