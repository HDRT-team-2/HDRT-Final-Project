<script setup lang="ts">
import Card from '@/components/common/Card.vue'
import FireScheduleTable from '@/components/sidebar/FireScheduleTable.vue'
import { storeToRefs } from 'pinia'
import { useFireStore } from '@/stores/fire'
import { computed } from 'vue'

// Fire Store 연결
const fireStore = useFireStore()
const { fires } = storeToRefs(fireStore)

// Store 데이터를 Table Props 형식으로 변환
const schedules = computed(() => {
  return fires.value.map(fire => ({
    id: fire.id,
    target_tracking_id: fire.target_tracking_id,
    firedAt: fire.firedAt
  }))
})
</script>

<template>
  <Card title="타격 스케줄링">
    <FireScheduleTable :schedules="schedules" />
  </Card>
</template>