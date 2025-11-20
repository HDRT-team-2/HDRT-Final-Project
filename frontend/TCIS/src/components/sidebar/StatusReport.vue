<script setup lang="ts">
import Card from '@/components/common/Card.vue'
import Badge from '@/components/common/Badge.vue'
import { storeToRefs } from 'pinia'
import { useStatusReportStore } from '@/stores/mission-status-store'
import { computed } from 'vue'

// Store 연결
const statusReportStore = useStatusReportStore()
const { statusReport } = storeToRefs(statusReportStore)

// 작전 상태에 따른 색상
const statusColor = computed<'green' | 'yellow' | 'red'>(() => {
  switch (statusReport.value.status) {
    case '방어':
      return 'green'
    case '수색':
      return 'yellow'
    case '공격':
      return 'red'
    default:
      return 'green'
  }
})
</script>
<template>
  <Card title="임무 상태">
    <div class="space-y-1">
      <!-- 작전 정보 -->
      <div class="p-2 flex items-center justify-between">
        <h5 class="font-semibold text-primary-800">
          {{ statusReport.operationName }} 
          <span class="text-xs">({{ statusReport.commander }})</span>
        </h5>
        <Badge :text="statusReport.status" :color="statusColor" />
      </div>

      <!-- 작전 목표 -->
      <div class="bg-gray-50 rounded p-2 border border-gray-200 text-sm whitespace-pre-line">
        <p>{{ statusReport.objective }}</p>
      </div>
    </div>
  </Card>
</template>