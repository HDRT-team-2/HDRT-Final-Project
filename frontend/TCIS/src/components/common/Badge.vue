<script setup lang="ts">
interface Props {
  text: string
  color?: 'rotem' | 'yellow' | 'danger' | 'success' | 'gray'
}

const props = withDefaults(defineProps<Props>(), {
  color: 'gray'
})

const colorClasses = {
  rotem: 'bg-rotem-500',
  yellow: 'bg-warning-700',
  danger: 'bg-danger-500',
  success: 'bg-success-500',
  gray: 'bg-gray-500'
}
</script>

<template>
  <span :class="colorClasses[color]" class="px-2 py-1 text-white text-xs rounded-full font-medium">
    {{ text }}
  </span>
</template>

<style scoped></style>