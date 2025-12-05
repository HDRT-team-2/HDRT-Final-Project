<script setup lang="ts">
import { ref, nextTick } from 'vue';
import Card from '@/components/common/Card.vue'
import CommandHistory from '@/components/commandPanel/CommandHistory.vue';
import CommandInput from '@/components/commandPanel/CommandInput.vue';
import { parseCommandWithLLM } from '@/services/llm-service';
import { useTargetCommand } from '@/composables/useTargetCommand';
import { useStatusReportStore } from '@/stores/mission-status-store';

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

const { sendTarget } = useTargetCommand();
const statusReportStore = useStatusReportStore();

// 히스토리 컨테이너 ref
const historyContainer = ref<HTMLElement | null>(null);

// 스크롤을 맨 아래로 이동
const scrollToBottom = () => {
  nextTick(() => {
    if (historyContainer.value) {
      historyContainer.value.scrollTop = historyContainer.value.scrollHeight;
    }
  });
};

// 명령어 입력 처리 (Frontend LLM 사용)
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
  scrollToBottom();

  try {
    // LLM으로 명령어 분석
    const result = await parseCommandWithLLM(command);
    
    // LLM 응답 추가
    commandHistory.value.push({
      id: commandIdCounter++,
      command: result.message,
      timestamp,
      type: result.type === 'error' ? 'error' : 'output'
    });
    scrollToBottom();

    // command 타입이면 좌표를 store에 저장하고 backend로 전송
    if (result.type === 'command' && result.x !== undefined && result.y !== undefined) {
      // Store에 목표 좌표 저장
      statusReportStore.setCommandTarget(result.x, result.y);
      
      // Backend로 전송
      await sendTarget();
      
      console.log(`[CommandPanel] Target 전송 완료: (${result.x}, ${result.y}), action: ${result.action}`);
    }
  } catch (error) {
    // 에러 처리
    commandHistory.value.push({
      id: commandIdCounter++,
      command: 'LLM 처리 중 오류가 발생했습니다',
      timestamp,
      type: 'error'
    });
    scrollToBottom();
    console.error('[CommandPanel] LLM 처리 오류:', error);
  }
};
</script>

<template>
  <Card title="지휘 보조 시스템">
    <div class="flex flex-col h-full overflow-hidden">
        <!-- 명령어 히스토리 -->
        <div ref="historyContainer" class="flex-1 overflow-auto min-h-0">
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
