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
  <div class="h-full bg-gray-800 p-2 flex flex-col">
    <!-- 입력창 -->
    <div class="flex-shrink-0 mb-2">
      <div class="relative">
        <span class="absolute left-2 top-1/2 transform -translate-y-1/2 text-blue-400 text-xs font-mono">></span>
        <input
          v-model="commandInput"
          @keypress="handleKeyPress"
          type="text"
          placeholder="명령어..."
          class="w-full bg-gray-700 text-white text-xs font-mono pl-6 pr-2 py-1 rounded border border-gray-600 focus:border-blue-500 focus:outline-none"
        />
      </div>
    </div>
    
    <!-- 상태 정보 (세로 공간 활용) -->
    <div class="flex-1 text-xs text-gray-400 space-y-1">
      <div>히스토리: {{ historyCount }}개</div>
      <div class="text-gray-500">Enter로 실행</div>
      <div class="text-gray-500">Shift+Enter로 줄바꿈</div>
    </div>
  </div>
</template>