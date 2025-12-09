<script setup lang="ts">
import { ref, nextTick } from 'vue';
import Card from '@/components/common/Card.vue'
import CommandHistory from '@/components/commandPanel/CommandHistory.vue';
import CommandInput from '@/components/commandPanel/CommandInput.vue';
import { parseCommandWithLLM } from '@/services/llm-service';
import { useTargetCommand } from '@/composables/useTargetCommand';
import { useStatusReportStore } from '@/stores/mission-status-store';
import { useDetectionStore } from '@/stores/detection-store';
import { usePositionStore } from '@/stores/position-store';
import { useFireStore } from '@/stores/fire-store';
import { storeToRefs } from 'pinia';

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
const detectionStore = useDetectionStore();
const positionStore = usePositionStore();
const fireStore = useFireStore();

// Store 데이터 가져오기
const { missionReport } = storeToRefs(statusReportStore);
const { objects } = storeToRefs(detectionStore);
const { myTanks } = storeToRefs(positionStore);
const { fires } = storeToRefs(fireStore);

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
    // 전역 데이터를 LLM 컨텍스트로 전달
    const currentMission = missionReport.value.mission === '방어' ? 'defense' : 'combat';
    const targetPos = missionReport.value.targetPosition;
    
    const result = await parseCommandWithLLM(command, {
      currentMission,
      detectedObjects: objects.value,
      myTanks: myTanks.value,
      targetPosition: targetPos ? { x: targetPos.x, y: targetPos.y } : undefined,
      fireHistory: fires.value
    });
    
    // LLM 응답 추가
    commandHistory.value.push({
      id: commandIdCounter++,
      command: result.message,
      timestamp,
      type: result.type === 'error' ? 'error' : 'output'
    });
    scrollToBottom();

    // command 타입이면 임무 변경 API 호출
    if (result.type === 'command' && result.x !== undefined && result.y !== undefined && result.mission) {
      // Store에 목표 좌표 및 임무 저장
      statusReportStore.setCommandTarget(result.x, result.y, result.mission);
      
      // Backend로 임무 변경 전송
      const success = await sendTarget();
      
      if (success) {
        console.log(`[CommandPanel] 임무 변경 완료: (${result.x}, ${result.y}), mission: ${result.mission}`);
      } else {
        commandHistory.value.push({
          id: commandIdCounter++,
          command: '임무 변경 전송에 실패했습니다',
          timestamp,
          type: 'error'
        });
        scrollToBottom();
      }
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
