<script setup lang="ts">
import ObjectItem from '@/components/common/ObjectItem.vue';
import { ref } from 'vue';

defineProps<{
    // { id: 1, name: '적군 3', type: '보병', x: 320, y: 240 },
  itemList: { id: number; name: string; type: string; x: number; y: number }[];
}>();
</script>
<template>
  <ul class="space-y-1">
    <ObjectItem
      v-for="item in itemList"
      :key="item.id"
      :id="item.id"
      :name="item.name"
      :type="item.type"
      :x="item.x"
      :y="item.y"
    />
  </ul>
</template>