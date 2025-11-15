<script setup lang="ts">
import Card from '@/components/common/Card.vue'
import ObjectsList from '@/components/common/ObjectsList.vue'
import { storeToRefs } from 'pinia'
import { useDetectionStore } from '@/stores/detection'
import { computed } from 'vue'

const detectionStore = useDetectionStore()
const { tankCount, mineCount, enemyCount, civilianCount, personCount, vehicleCount } = storeToRefs(detectionStore)

const tankItems = computed(() => [
  { label: '전차', count: tankCount.value },
  { label: '보병', count: personCount.value },
  { label: '지뢰', count: mineCount.value }
])

const civilianItems = computed(() => [
  { label: '차량', count: vehicleCount.value }
])
</script>

<template>
  <Card title="탐지 객체">
    <div class="text-sm flex gap-3">
      <!-- 적 전차 -->
      <ObjectsList
        title="적"
        :count="enemyCount"
        bg-color="bg-red-50"
        border-color="border-red-200"
        text-color="text-red-700"
        count-color="text-red-600"
        :items="tankItems"
        class="flex-1"
      />
      
      <!-- 민간 -->
      <ObjectsList
        title="민간"
        :count="civilianCount"
        bg-color="bg-blue-50"
        border-color="border-blue-200"
        text-color="text-blue-700"
        count-color="text-blue-600"
        :items="civilianItems"
        class="flex-1"
      />
    </div>
  </Card>
</template>