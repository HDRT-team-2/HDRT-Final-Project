<script setup lang="ts">
import Card from '@/components/common/Card.vue';
import ObjectsList from '@/components/common/ObjectsList.vue';

const enemies = [
  { id: 1, name: '적군 1', type: '탱크', x: 120, y: 340 },
  { id: 2, name: '적군 2', type: '보병', x: 220, y: 140 },
  { id: 3, name: '적군 3', type: '보병', x: 320, y: 240 },
];

const allies = [
  { id: 1, name: '아군 1', type: '헬기', x: 520, y: 440 },
  { id: 2, name: '아군 2', type: '보병', x: 620, y: 540 },
  { id: 3, name: '아군 3', type: '탱크', x: 720, y: 640 },
];

</script>
<template>
  <Card title="탐지 객체">
    <div class="flex flex-col gap-2">
        <ObjectsList :itemList="enemies" />
        <ObjectsList :itemList="allies" />
    </div>
    </Card>
</template>