<script setup lang="ts">
defineProps<{ title: string }>()
</script>

<template>
  <div class="border border-rotem-100 rounded-lg shadow-sm hover:shadow-md w-full">
    <!-- Header -->
    <div class="bg-gradient-to-b from-rotem-600 to-rotem-500 border-b rounded-t-lg border-rotem-200 px-4 py-3">
      <h3 class="text-sm font-bold text-rotem-50 m-0 tracking-wide">{{ title }}</h3>
    </div>
    
    <!-- Body -->
    <div class="p-2 overflow-y-auto">
      <slot />
    </div>
  </div>
</template>