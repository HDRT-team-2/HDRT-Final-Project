<script setup lang="ts">
import Card from '@/components/common/Card.vue'
import Badge from '@/components/common/Badge.vue'
import { storeToRefs } from 'pinia'
import { useStatusReportStore } from '@/stores/mission-status-store'
import { computed } from 'vue'

// Store 연결
const statusReportStore = useStatusReportStore()
const { missionReport } = storeToRefs(statusReportStore)

// 작전 상태에 따른 색상
const statusColor = computed<'success' | 'yellow' | 'danger'>(() => {
  switch (missionReport.value.mission) {
    case '방어':
      return 'success'
    case '수색':
      return 'yellow'
    case '공격':
      return 'danger'
    default:
      return 'success'
  }
})
</script>
<template>
  <Card title="임무 상태">
    <div class="space-y-1">
      <!-- 작전 정보 -->
      <div class="p-2 flex items-center justify-between">
        <h5 class="font-semibold text-primary-800">
          {{ missionReport.operationName }} 
          <span class="text-xs">({{ missionReport.commander }})</span>
        </h5>
        <Badge :text="missionReport.mission" :color="statusColor" />
      </div>

      <!-- 작전 목표 -->
      <div class="bg-gray-50 rounded p-2 border border-gray-200 text-sm whitespace-pre-line">
        <p>{{ missionReport.objective }}</p>
      </div>
    </div>
  </Card>
</template>