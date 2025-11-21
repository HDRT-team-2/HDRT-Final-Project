import { ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useStatusReportStore } from '@/stores/mission-status-store'
import { usePositionStore } from '@/stores/position-store'
import { parseCommandWithLLM, type LLMCommandResult } from '@/services/llm-service'

export interface ChatResponse {
  type: 'command' | 'answer' | 'error'
  message: string
  x?: number
  y?: number
  action?: 'move' | 'attack' | 'move_and_fire'
}

/**
 * LLM 채팅 명령 처리 (Frontend에서 직접)
 */
export function useChatCommand() {
  const statusReportStore = useStatusReportStore()
  const positionStore = usePositionStore()
  const { current: currentPos } = storeToRefs(positionStore)
  const { missionReport } = storeToRefs(statusReportStore)
  
  const isSending = ref(false)
  const error = ref<string | null>(null)
  
  /**
   * 채팅 메시지 전송 (Frontend LLM 처리)
   */
  async function sendChatMessage(message: string): Promise<ChatResponse | null> {
    if (!message.trim()) {
      error.value = '메시지를 입력해주세요'
      return null
    }
    
    isSending.value = true
    error.value = null
    
    try {
      // 현재 컨텍스트 구성
      const context = {
        currentPos: currentPos.value ? {
          x: currentPos.value.x,
          y: currentPos.value.y
        } : undefined,
        targetPos: missionReport.value.targetPosition ? {
          x: missionReport.value.targetPosition.x,
          y: missionReport.value.targetPosition.y
        } : undefined
      }

      // LLM으로 명령 분석
      const result = await parseCommandWithLLM(message, context)
      
      // command 타입이면 target 설정 및 backend로 전송
      if (result.type === 'command' && result.x !== undefined && result.y !== undefined) {
        // action에 따라 mission 결정
        const mission = result.action === 'attack' || result.action === 'move_and_fire' 
          ? 'attack_n_search' 
          : 'defend'
        
        statusReportStore.setCommandTarget(result.x, result.y, mission)
        console.log(`[LLM] 목표 위치 설정: (${result.x}, ${result.y}), action: ${result.action}, mission: ${mission}`)
        
        // Backend로 target 전송 (useTargetCommand 통해 자동 전송됨)
      }
      
      return result
      
    } catch (err) {
      error.value = `메시지 처리 실패: ${err instanceof Error ? err.message : '알 수 없는 오류'}`
      console.error('채팅 명령 실패:', err)
      return {
        type: 'error',
        message: '명령 처리 중 오류가 발생했습니다.'
      }
      
    } finally {
      isSending.value = false
    }
  }
  
  return {
    isSending,
    error,
    sendChatMessage
  }
}