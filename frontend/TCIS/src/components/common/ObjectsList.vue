<script setup lang="ts">
import ObjectListItem from '@/components/common/ObjectListItem.vue'

interface Props {
  title: string
  count: number
  bgColor: string
  borderColor: string
  textColor: string
  countColor: string
  items?: { label: string; count: number }[] // 하위 항목 (옵션)
}

defineProps<Props>()
</script>

<template>
  <div :class="['p-2 border rounded', bgColor, borderColor]">
    <div class="flex items-center justify-between" :class="{ 'mb-2': items }">
      <span :class="['font-medium', textColor]">{{ title }}</span>
      <span :class="['text-lg font-bold', countColor]">{{ count }}</span>
    </div>
    
    <!-- 하위 항목 -->
    <div v-if="items" class="pl-4 space-y-1">
      <ObjectListItem 
        v-for="(item, index) in items" 
        :key="index"
        :label="item.label"
        :count="item.count"
      />
    </div>
  </div>
</template>