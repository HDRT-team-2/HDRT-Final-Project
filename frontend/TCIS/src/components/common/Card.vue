<script setup lang="ts">
defineProps<{ title: string }>()
</script>

<template>
  <div class="border border-rotem-100 rounded-lg shadow-sm shadow-md w-full h-full flex flex-col">
    <!-- Header -->
    <div class="bg-gradient-to-b from-rotem-800 to-rotem-600 border-b rounded-t-lg border-rotem-100 px-4 py-3">
      <h3 class="text-sm font-bold text-rotem-50 m-0 tracking-wide">{{ title }}</h3>
    </div>
    
    <!-- Body -->
    <div class="p-2 overflow-y-auto flex-1">
      <slot />
    </div>
  </div>
</template>