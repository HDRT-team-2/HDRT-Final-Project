<script setup lang="ts">
interface Props {
  label: string  // "사람" or "차량"
  count: number  // 개수
}

defineProps<Props>()
</script>

<template>
  <div class="flex justify-between text-xs">
    <span>• {{ label }}</span>
    <span class="font-semibold">{{ count }}</span>
  </div>
</template>