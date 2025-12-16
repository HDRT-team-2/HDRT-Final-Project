<script setup lang="ts">
interface Props {
  modelValue: string | number;
  maxlength?: number;
  placeholder?: string;
  label?: string;
}

interface Emits {
  (e: 'update:modelValue', value: string): void;
  (e: 'blur'): void;
}

const props = withDefaults(defineProps<Props>(), {
  maxlength: 7,
  placeholder: '000.000'
});

const emit = defineEmits<Emits>();

const handleInput = (event: Event) => {
  const target = event.target as HTMLInputElement;
  emit('update:modelValue', target.value);
};

const handleBlur = () => {
  emit('blur');
};
</script>

<template>
  <div class="flex items-center gap-1 pt-1">
    <label v-if="label" class="text-sm font-medium text-gray-700 w-4">
      {{ label }}:
    </label>
    <input 
      :value="modelValue"
      @input="handleInput"
      @blur="handleBlur"
      type="number"
      :maxlength="maxlength"
      :placeholder="placeholder"
      class="w-[4.3rem] text-center 
      border-0 border-b-2 border-gray-300 focus:border-primary-500 focus:outline-none bg-transparent 
      text-sm font-mono 
      [&::-webkit-outer-spin-button]:w-2 [&::-webkit-inner-spin-button]:w-2"
    />
  </div>
</template>