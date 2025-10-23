<script setup lang="ts">
interface Props {
  id: number,
  name: string,
  type: string,
  x: number,
  y: number
}

defineProps<Props>()
</script>
<template>
  <li class="text-xs bg-gray-50 rounded px-2 py-1 border border-gray-200 hover:bg-gray-100 transition-colors">
    <div class="font-medium">{{ name }}</div>
    <div class="text-gray-600">{{ type }} [{{ String(x).padStart(3, '0') }}, {{ String(y).padStart(3, '0') }}]</div>
  </li>
</template>