<script setup lang="ts">
import BaseTable from '@/components/common/BaseTable.vue'
import Badge from '@/components/common/Badge.vue'
import type { FireEvent } from '@/types/fire'
import { CLASS_NAME_KR } from '@/types/detection'

// Props 정의
interface Props {
  fires: FireEvent[]
}

const props = defineProps<Props>()

const columns = [
  { key: 'time', label: '시간', align: 'center' as const, width: '100px' },
  { key: 'ally', label: '아군', align: 'center' as const, width: '80px' },
  { key: 'enemy', label: '적군', align: 'center' as const, width: '120px' },
  { key: 'result', label: '사격결과', align: 'center' as const, width: '80px' }
]

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
    :data="props.fires"
    :striped="false"
    :bordered="true"
    :hover="false"
    size="sm"
  >
    <!-- 시간 컴럼 -->
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