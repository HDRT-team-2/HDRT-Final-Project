<script setup lang="ts">
import { ref } from 'vue';
import CommandHeader from '@/components/commandPanel/CommandHeader.vue';
import CommandHistory from '@/components/commandPanel/CommandHistory.vue';
import CommandInput from '@/components/commandPanel/CommandInput.vue';
import { useChatCommand } from '@/composables/useChatCommand';  // ← 추가

interface CommandEntry {
  id: number;
  command: string;
  timestamp: string;
  type: 'input' | 'output' | 'error';
}

const commandHistory = ref<CommandEntry[]>([
  { id: 1, command: '시스템 초기화 완료', timestamp: '14:20', type: 'output' },
]);

let commandIdCounter = 2;

// Chat Command Composable 사용
const { sendChatMessage, isSending } = useChatCommand();

// 명령어 입력 처리
const handleCommandSubmit = async (command: string) => { 
  const now = new Date();
  const timestamp = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`;
  
  // 입력된 명령어 추가
  commandHistory.value.push({
    id: commandIdCounter++,
    command: command,
    timestamp,
    type: 'input'
  });

  // Backend로 전송
  const result = await sendChatMessage(command);
  
  if (result) {
    // Backend 응답 추가
    commandHistory.value.push({
      id: commandIdCounter++,
      command: result.message,
      timestamp,
      type: result.type === 'error' ? 'error' : 'output'
    });
  } else {
    // 에러 처리
    commandHistory.value.push({
      id: commandIdCounter++,
      command: '서버 오류가 발생했습니다',
      timestamp,
      type: 'error'
    });
  }
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
