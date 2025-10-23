<script setup lang="ts">
import { computed } from 'vue';

interface Props {
  label: string;
  value: string | number;
  maxlength?: number;
}

const props = withDefaults(defineProps<Props>(), {
  maxlength: 3
});

// 값을 zero-padding으로 포맷팅
const formattedValue = computed(() => {
  return String(props.value).padStart(props.maxlength, '0');
});
</script>

<template>
  <div class="flex items-center gap-2">
    <label class="text-sm font-medium text-gray-700 w-4">
      {{ label }}:
    </label>
    <div class="w-12 text-center text-sm font-mono py-1 text-gray-800 font-semibold">
      {{ formattedValue }}
    </div>
  </div>
</template>