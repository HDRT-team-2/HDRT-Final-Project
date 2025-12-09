<script setup lang="ts">
import Card from '@/components/common/Card.vue'
import LabelText from '@/components/common/LabelText.vue'
import { computed } from 'vue'

// pinia
import { storeToRefs } from 'pinia'
import { useStatusReportStore } from '@/stores/mission-status-store'

// Store 연결
const statusReportStore = useStatusReportStore()
// 반응형으로 commandTarget 가져오기
const { commandTarget } = storeToRefs(statusReportStore)

// X 위치 값
const xPosition = computed(() => {
  if (commandTarget.value && typeof commandTarget.value.x === 'number') {
    return commandTarget.value.x.toFixed(3)
  }
  return '0.000'
})

// Y 위치 값
const yPosition = computed(() => {
  if (commandTarget.value && typeof commandTarget.value.y === 'number') {
    return commandTarget.value.y.toFixed(3)
  }
  return '0.000'
})
</script>

<template>
  <Card title="목표 위치">
    <div class="flex items-center justify-center gap-2">
      <LabelText 
        label="X"
        :value="xPosition"
        :maxlength="7"
      />
      
      <LabelText 
        label="Y" 
        :value="yPosition"
        :maxlength="7"
      />
    </div>
  </Card>
</template>
