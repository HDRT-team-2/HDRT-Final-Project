<script setup lang="ts">
defineProps<{
  title?: string;
}>();
</script>

<template>
  <div class="bg-gray-800 px-3 py-1 border-b border-gray-700">
    <h2 class="text-xs font-bold text-gray-200">{{ title || '명령어 콘솔' }}</h2>
  </div>
</template>