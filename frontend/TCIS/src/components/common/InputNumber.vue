<script setup lang="ts">
interface Props {
  modelValue: string | number;
  maxlength?: number;
  placeholder?: string;
  label?: string;
}

interface Emits {
  (e: 'update:modelValue', value: string): void;
}

const props = withDefaults(defineProps<Props>(), {
  maxlength: 3,
  placeholder: '000'
});

const emit = defineEmits<Emits>();

const handleInput = (event: Event) => {
  const target = event.target as HTMLInputElement;
  emit('update:modelValue', target.value);
};
</script>

<template>
  <div class="flex items-center gap-2">
    <label v-if="label" class="text-sm font-medium text-gray-700 w-4">
      {{ label }}:
    </label>
    <input 
      :value="modelValue"
      @input="handleInput"
      type="number"
      :maxlength="maxlength"
      :placeholder="placeholder"
      class="w-12 text-center border-0 border-b-2 border-gray-300 focus:border-primary-500 focus:outline-none bg-transparent text-sm font-mono"
    />
  </div>
</template>