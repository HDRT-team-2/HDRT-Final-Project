<script setup lang="ts">
import { watch } from 'vue';

// Pinia
import { storeToRefs } from 'pinia'
import { usePositionStore } from '@/stores/position-store'
import { useDetectionStore } from '@/stores/detection-store';
import MapCanvas from './MapCanvas.vue';

// Store 연결
const positionStore = usePositionStore()
const detectionStore = useDetectionStore()

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
}, { immediate: true, deep: true });

// 반응형으로 objects 가져오기
const { objects } = storeToRefs(detectionStore)
watch(objects, (newObjects) => {
  console.log('탐지된 객체들 변경됨:', newObjects);
}, { immediate: true });

</script>
<template>
  <div class="w-full h-full flex items-center justify-center p-2">
    <MapCanvas
      :current="current"
      :target="target"
      :objects="objects"
    />
  </div>
</template>