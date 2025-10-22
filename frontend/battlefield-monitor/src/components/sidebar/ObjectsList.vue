<script setup lang="ts">
import ObjectItem from '@/components/sidebar/ObjectItem.vue';
import { ref } from 'vue';

const itemList = ref([
    { id: 1, name: '객체 1' },
    { id: 2, name: '객체 2' },
    { id: 3, name: '객체 3' },
]);
</script>
<template>
  <ul>
    <ObjectItem
      v-for="item in itemList"
      :key="item.id"
      :name="item.name"
    />
  </ul>
</template>