<script setup lang="ts">
import Card from '@/components/common/Card.vue'
import ObjectsList from '@/components/common/ObjectsList.vue'
import { storeToRefs } from 'pinia'
import { useDetectionStore } from '@/stores/detection-store'
import { computed } from 'vue'

const detectionStore = useDetectionStore()
const { 
  enemyCount, enemyTankCount, enemyInfantryCount,
  allyCount, allyTankCount, allyInfantryCount,
  otherCount, vehicleCount, rockCount
} = storeToRefs(detectionStore)

const enemyItems = computed(() => [
  { label: '전차', count: enemyTankCount.value },
  { label: '보병', count: enemyInfantryCount.value }
])

const allyItems = computed(() => [
  { label: '전차', count: allyTankCount.value },
  { label: '보병', count: allyInfantryCount.value }
])

const otherItems = computed(() => [
  { label: '차량', count: vehicleCount.value },
  { label: '바위', count: rockCount.value }
])
</script>

<template>
  <Card title="탐지 객체">
    <div class="text-sm flex gap-3 h-full">
      <!-- 적 -->
      <ObjectsList
        title="적"
        :count="enemyCount"
        bg-color="bg-danger-50"
        border-color="border-danger-200"
        text-color="text-danger-500"
        count-color="text-danger-500"
        :items="enemyItems"
        class="flex-1"
      />
      
      <!-- 아군 -->
      <ObjectsList
        title="아군"
        :count="allyCount"
        bg-color="bg-rotem-50"
        border-color="border-rotem-200"
        text-color="text-rotem-500"
        count-color="text-rotem-500"
        :items="allyItems"
        class="flex-1"
      />
      
      <!-- 기타 -->
      <ObjectsList
        title="기타"
        :count="otherCount"
        bg-color="bg-success-50"
        border-color="border-success-200"
        text-color="text-success-600"
        count-color="text-success-600"
        :items="otherItems"
        class="flex-1"
      />
    </div>
  </Card>
</template>