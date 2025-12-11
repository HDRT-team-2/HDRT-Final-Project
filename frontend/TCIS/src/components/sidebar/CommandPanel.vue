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
    
    
    // 모든 class_name 종류 확인
    const classNames = new Set(objects.value.map(o => o.class_name));
    
    // 각 class_name별 개수
    const classCounts: Record<string, number> = {};
    objects.value.forEach(obj => {
      classCounts[obj.class_name] = (classCounts[obj.class_name] || 0) + 1;
    });
    
    const obstacles = objects.value.filter(obj => ['rock_small', 'rock_large', 'wall', 'mine', 'other'].includes(obj.class_name));
    
    const result = await parseCommandWithLLM(command, {
      currentMission,
      detectedObjects: objects.value,
      myTanks: myTanks.value,
      targetPosition: targetPos ? { x: targetPos.x, y: targetPos.y } : undefined,
      fireHistory: fires.value,
      operationName: missionReport.value.operationName,
      commander: missionReport.value.commander
    });
    
    // multi 타입이면 각 명령을 순서대로 처리
    if (result.type === 'multi' && result.commands && result.commands.length > 0) {
      commandHistory.value.push({
        id: commandIdCounter++,
        command: result.message,
        timestamp,
        type: 'output'
      });
      scrollToBottom();
      
      // 각 명령을 순서대로 처리
      for (const cmd of result.commands) {
        const singleResult = { ...cmd, type: cmd.type as any, message: cmd.message || '' };
        await handleSingleCommand(singleResult);
      }
      return;
    }
    
    // 단일 명령 처리
    await handleSingleCommand(result);
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

// 단일 명령 처리 함수
const handleSingleCommand = async (result: any) => {
    const now = new Date();
    const timestamp = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`;
    
    // relative_command 타입이면 좌표 계산
    if (result.type === 'relative_command' && result.target && result.mission) {
      const myPos = myTanks.value.length > 0 ? myTanks.value[0] : { x: 0, y: 0 };
      
      // 대상 적 필터링
      let enemies = objects.value.filter(obj => obj.alive);
      if (result.targetType === 'tank') {
        enemies = enemies.filter(obj => obj.class_name === 'tank' || obj.class_name === 'tank_around');
      } else if (result.targetType === 'infantry') {
        enemies = enemies.filter(obj => obj.class_name === 'human' || obj.class_name === 'human_around');
      } else {
        // any: 전차 또는 보병
        enemies = enemies.filter(obj => 
          ['tank', 'tank_around', 'human', 'human_around'].includes(obj.class_name)
        );
      }
      
      if (enemies.length === 0) {
        commandHistory.value.push({
          id: commandIdCounter++,
          command: '대상 적이 없습니다',
          timestamp,
          type: 'error'
        });
        scrollToBottom();
      } else {
        let targetEnemy;
        
        if (result.target === 'closest_enemy') {
          // 가장 가까운 적
          targetEnemy = enemies.reduce((closest, enemy) => {
            const distCurrent = Math.hypot(enemy.position.x - myPos.x, enemy.position.y - myPos.y);
            const distClosest = Math.hypot(closest.position.x - myPos.x, closest.position.y - myPos.y);
            return distCurrent < distClosest ? enemy : closest;
          });
        } else if (result.target === 'farthest_enemy') {
          // 가장 먼 적
          targetEnemy = enemies.reduce((farthest, enemy) => {
            const distCurrent = Math.hypot(enemy.position.x - myPos.x, enemy.position.y - myPos.y);
            const distFarthest = Math.hypot(farthest.position.x - myPos.x, farthest.position.y - myPos.y);
            return distCurrent > distFarthest ? enemy : farthest;
          });
        } else if (result.target === 'center_enemy') {
          // 지도 중앙(150, 150)에 가장 가까운 적
          const centerX = 150, centerY = 150;
          targetEnemy = enemies.reduce((closest, enemy) => {
            const distCurrent = Math.hypot(enemy.position.x - centerX, enemy.position.y - centerY);
            const distClosest = Math.hypot(closest.position.x - centerX, closest.position.y - centerY);
            return distCurrent < distClosest ? enemy : closest;
          });
        } else if (result.target === 'topmost_enemy') {
          // 최상단 (y 최대)
          targetEnemy = enemies.reduce((topmost, enemy) => 
            enemy.position.y > topmost.position.y ? enemy : topmost
          );
        } else if (result.target === 'bottommost_enemy') {
          // 최하단 (y 최소)
          targetEnemy = enemies.reduce((bottommost, enemy) => 
            enemy.position.y < bottommost.position.y ? enemy : bottommost
          );
        } else if (result.target === 'leftmost_enemy') {
          // 최좌측 (x 최소)
          targetEnemy = enemies.reduce((leftmost, enemy) => 
            enemy.position.x < leftmost.position.x ? enemy : leftmost
          );
        } else if (result.target === 'rightmost_enemy') {
          // 최우측 (x 최대)
          targetEnemy = enemies.reduce((rightmost, enemy) => 
            enemy.position.x > rightmost.position.x ? enemy : rightmost
          );
        }
        
        if (targetEnemy) {
          const targetX = Math.round(targetEnemy.position.x);
          const targetY = Math.round(targetEnemy.position.y);
          
          // 계산된 좌표로 command 실행
          result.type = 'command';
          result.x = targetX;
          result.y = targetY;
          result.message = `${result.message || '목표 설정'} - 목표: (${targetX}, ${targetY})`;
        }
      }
    }
    
    // config 타입이면 작전명/지휘관 변경
    if (result.type === 'config') {
      if (result.operationName) {
        statusReportStore.setOperationName(result.operationName);
      }
      if (result.commander) {
        statusReportStore.setCommander(result.commander);
      }
    }
    
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
