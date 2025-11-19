<script setup lang="ts">
import { ref, nextTick, watch } from 'vue';

interface CommandEntry {
  id: number;
  command: string;
  timestamp: string;
  type: 'input' | 'output' | 'error';
}

const props = defineProps<{
  history: CommandEntry[];
}>();

const historyContainer = ref<HTMLElement>();

// 명령어 타입별 스타일
const getCommandStyle = (type: string) => {
  switch (type) {
    case 'input':
      return 'text-blue-700 bg-blue-50 border-l-4 border-blue-400';
    case 'output':
      return 'text-green-700 bg-green-50 border-l-4 border-green-400';
    case 'error':
      return 'text-red-700 bg-red-50 border-l-4 border-red-400';
    default:
      return 'text-gray-700 bg-gray-50 border-l-4 border-gray-400';
  }
};

// 스크롤을 맨 아래로
const scrollToBottom = () => {
  nextTick(() => {
    if (historyContainer.value) {
      historyContainer.value.scrollTop = historyContainer.value.scrollHeight;
    }
  });
};

// 히스토리가 변경될 때마다 스크롤
watch(() => props.history.length, () => {
  scrollToBottom();
});
</script>

<template>
  <div 
    ref="historyContainer"
    class="h-full overflow-y-auto py-2 space-y-1"
  >
    <div 
      v-for="entry in history"
      :key="entry.id"
      class="rounded px-2 py-1 text-xs font-mono"
      :class="getCommandStyle(entry.type)"
    >
      <div class="flex flex-row items-start gap-2">
        <span class="font-semibold mr-1 self-start min-w-[16px] text-center">
          {{ entry.type === 'input' ? '>' : entry.type === 'error' ? '!' : '<' }}
        </span>
        <div class="flex-1 min-w-0">
          <div class="flex justify-between items-baseline mb-1">
            <span class="text-xs opacity-75">{{ entry.timestamp }}</span>
          </div>
          <div class="leading-relaxed break-words">{{ entry.command }}</div>
        </div>
      </div>
    </div>
  </div>
</template>