<script setup lang="ts">
import { watch } from 'vue';

// Pinia
import { storeToRefs } from 'pinia'
import { usePositionStore } from '@/stores/position'

// Store 연결
const positionStore = usePositionStore()

// 반응형으로 current 가져오기
const { current } = storeToRefs(positionStore)
console.log('현재 내 전차 위치:', current.value.x, current.value.y);

// 반응형으로 target 가져오기
const { target } = storeToRefs(positionStore)
watch(target, (newTarget) => {
  if (newTarget) {
    console.log('목표 위치 변경됨:', newTarget.x, newTarget.y);
  } else {
    console.log('목표 위치가 제거됨');
  }
}, { immediate: true });

</script>
<template>
  <div class="battlefield-map">
    <h2>Battlefield Map</h2>
    <!-- Map rendering logic goes here -->
  </div>
</template>