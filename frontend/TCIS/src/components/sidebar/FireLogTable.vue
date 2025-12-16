<script setup lang="ts">
import BaseTable from '@/components/common/BaseTable.vue'
import Badge from '@/components/common/Badge.vue'
import type { FireEvent } from '@/types/fire'
import { CLASS_NAME_KR } from '@/types/detection'
import { ref, computed } from 'vue'

// Props 정의
interface Props {
  fires: FireEvent[]
}

const props = defineProps<Props>()

// 시간 정렬 상태 (기본값: desc = 최신 순)
const timeSortOrder = ref<'asc' | 'desc'>('desc')

// 정렬된 fires 배열 (시간 기준, 최신이 위로)
const sortedFires = computed(() => {
  const firesCopy = [...props.fires]
  
  if (timeSortOrder.value === 'asc') {
    // 오름차순: 오래된 것이 위로 (시간 작은 것 먼저)
    return firesCopy.sort((a, b) => a.firedAt.getTime() - b.firedAt.getTime())
  } else {
    // 내림차순: 최신 것이 위로 (시간 큰 것 먼저) - 기본값
    return firesCopy.sort((a, b) => b.firedAt.getTime() - a.firedAt.getTime())
  }
})

// BaseTable의 sort 이벤트 핸들러
const handleSort = (columnKey: string) => {
  if (columnKey === 'time') {
    timeSortOrder.value = timeSortOrder.value === 'asc' ? 'desc' : 'asc'
  }
}

// 컬럼 정의
const columns = computed(() => [
  { key: 'time', label: '시간', align: 'center' as const, width: '100px', sortable: true, sortOrder: timeSortOrder.value },
  { key: 'ally', label: '아군', align: 'center' as const, width: '80px' },
  { key: 'enemy', label: '적군', align: 'center' as const, width: '120px' },
  { key: 'result', label: '사격결과', align: 'center' as const, width: '80px' }
])

// 시간 포맷 (YY/MM/DD<br/>HH:MM:SS)
const formatTime = (date: Date) => {
  const year = String(date.getFullYear()).slice(-2)
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  const seconds = String(date.getSeconds()).padStart(2, '0')
  
  return `${year}/${month}/${day}<br/>${hours}:${minutes}:${seconds}`
}

// 적군 텍스트 (클래스 + ID)
const formatEnemy = (fire: any) => {
  const className = fire.target_class_name
  if (!className) return `ID: ${fire.target_tracking_id}`
  
  const koreanName = CLASS_NAME_KR[className as keyof typeof CLASS_NAME_KR] || className
  return `${koreanName} [${fire.target_tracking_id}]`
}
</script>

<template>
  <BaseTable 
    :columns="columns" 
    :data="sortedFires"
    :striped="false"
    :bordered="true"
    :hover="false"
    size="sm"
    @sort="handleSort"
  >
      <!-- 시간 컬럼 -->
      <template #time="{ row }">
        <span class="font-mono leading-tight" v-html="formatTime(row.firedAt)"></span>
      </template>
    
    <!-- 아군 컴럼 -->
    <template #ally="{ row }">
      <span class="">{{ row.ally_id }}</span>
    </template>
    
    <!-- 적군 컴럼 -->
    <template #enemy="{ row }">
      <span class="">{{ formatEnemy(row) }}</span>
    </template>
    
    <!-- 사격결과 컴럼 -->
    <template #result="{ row }">
      <Badge 
        v-if="row.result"
        :text="row.result === 'hit' ? '명중' : '비명중'"
        :color="row.result === 'hit' ? 'success' : 'danger'"
      />
      <span v-else class="text-gray-400 text-xs">대기중</span>
    </template>
    
    <!-- 빈 상태 -->
    <template #empty>
      <div class="text-gray-500 text-sm">
        발포 기록이 없습니다.
      </div>
    </template>
  </BaseTable>
</template>