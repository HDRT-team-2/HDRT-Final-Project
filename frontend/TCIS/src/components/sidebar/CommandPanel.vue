<script setup lang="ts">
import { ref } from 'vue';
import Card from '@/components/common/Card.vue'
import CommandHeader from '@/components/commandPanel/CommandHeader.vue';
import CommandHistory from '@/components/commandPanel/CommandHistory.vue';
import CommandInput from '@/components/commandPanel/CommandInput.vue';
import { useChatCommand } from '@/composables/useChatCommand';
import { useTargetCommand } from '@/composables/useTargetCommand';

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

// Chat Command Composable 사용 (Frontend LLM)
const { sendChatMessage, isSending } = useChatCommand();
const { sendTarget } = useTargetCommand();

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

  // Frontend LLM으로 분석
  const result = await sendChatMessage(command);
  
  if (result) {
    // LLM 응답 추가
    commandHistory.value.push({
      id: commandIdCounter++,
      command: result.message,
      timestamp,
      type: result.type === 'error' ? 'error' : 'output'
    });

    // command 타입이면 backend로 target 전송
    if (result.type === 'command' && result.x !== undefined && result.y !== undefined) {
      await sendTarget();
      console.log(`[CommandPanel] Target 전송 완료: (${result.x}, ${result.y})`)
    }
  } else {
    // 에러 처리
    commandHistory.value.push({
      id: commandIdCounter++,
      command: 'LLM 처리 중 오류가 발생했습니다',
      timestamp,
      type: 'error'
    });
  }
};
</script>

<template>
  <Card title="지휘 보조 시스템">
    <div class="flex flex-col h-full overflow-hidden">
        <!-- 명령어 히스토리 -->
        <div class="flex-1 overflow-auto min-h-0">
          <CommandHistory :history="commandHistory" />
        </div>
        
        <!-- 입력 영역 -->
        <div class="flex-shrink-0">
          <CommandInput 
            :history-count="commandHistory.length"
            @submit="handleCommandSubmit"
          />
        </div>
      </div>
  </Card>
</template>
