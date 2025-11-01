<script setup lang="ts">
defineProps<{ title: string }>()
</script>

<template>
  <div class="border border-gray-300 rounded-lg shadow-sm hover:shadow-md w-full">
    <!-- Header -->
    <div class="bg-military-300 border-b border-gray-200 px-4 py-3">
      <h3 class="text-sm font-bold text-gray-800 m-0 tracking-wide">{{ title }}</h3>
    </div>
    
    <!-- Body -->
    <div class="p-2 overflow-y-auto">
      <slot />
    </div>
  </div>
</template>