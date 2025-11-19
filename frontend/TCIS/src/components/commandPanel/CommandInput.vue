<script setup lang="ts">
import { ref } from 'vue';

const commandInput = ref('');

const emit = defineEmits<{
  submit: [command: string];
}>();

defineProps<{
  historyCount: number;
}>();

// 명령어 실행
const handleSubmitCommand = () => {
  if (!commandInput.value.trim()) return;
  
  emit('submit', commandInput.value.trim());
  commandInput.value = '';
};

// Enter 키로 명령어 실행
const handleKeyPress = (event: KeyboardEvent) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    handleSubmitCommand();
  }
};
</script>

<template>
  <!-- 입력창 -->
    <input
      v-model="commandInput"
      @keypress="handleKeyPress"
      type="text"
      placeholder="텍스트 입력.."
      class="w-full text-xs p-2 rounded-lg border border-rotem-200"
    />
</template>