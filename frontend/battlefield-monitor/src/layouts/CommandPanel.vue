<script setup lang="ts">
import { ref } from 'vue';
import CommandHeader from '@/components/commandPanel/CommandHeader.vue';
import CommandHistory from '@/components/commandPanel/CommandHistory.vue';
import CommandInput from '@/components/commandPanel/CommandInput.vue';

interface CommandEntry {
  id: number;
  command: string;
  timestamp: string;
  type: 'input' | 'output' | 'error';
}

const commandHistory = ref<CommandEntry[]>([
  { id: 1, command: '시스템 초기화 완료', timestamp: '14:20', type: 'output' },
  { id: 2, command: '전투 준비 상태 확인', timestamp: '14:22', type: 'input' },
  { id: 3, command: '전투 준비 완료 - 모든 시스템 정상', timestamp: '14:22', type: 'output' },
]);

let commandIdCounter = 4;

// 명령어 입력 처리
const handleCommandSubmit = (command: string) => {
  const now = new Date();
  const timestamp = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`;
  
  // 입력된 명령어 추가
  commandHistory.value.push({
    id: commandIdCounter++,
    command: command,
    timestamp,
    type: 'input'
  });

  // 시뮬레이션된 응답 추가 (실제로는 서버 응답)
  setTimeout(() => {
    commandHistory.value.push({
      id: commandIdCounter++,
      command: `명령어 "${command}" 처리 완료`,
      timestamp,
      type: 'output'
    });
  }, 500);
};
</script>

<template>
  <div class="flex flex-col min-h-[160px] bg-gray-900 text-white">
    <!-- 헤더 -->
    <CommandHeader title="명령어 콘솔" />

    <!-- 좌우 레이아웃: 히스토리 + 입력창 -->
    <div class="flex flex-1 min-h-0">
      <!-- 명령어 히스토리 (좌측, 넓은 영역) -->
      <div class="flex-1 min-w-0">
        <CommandHistory :history="commandHistory" />
      </div>
      
      <!-- 입력 영역 (우측, 좁은 영역) -->
      <div class="w-96 border-l border-gray-700">
        <CommandInput 
          :history-count="commandHistory.length"
          @submit="handleCommandSubmit"
        />
      </div>
    </div>
  </div>
</template>
