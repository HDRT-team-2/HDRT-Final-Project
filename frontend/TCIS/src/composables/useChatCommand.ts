import { ref } from 'vue'
import { useStatusReportStore } from '@/stores/mission-status-store'
import { ApiService } from '@/services/api_service'

export interface ChatResponse {
  type: 'command' | 'answer' | 'error'
  message: string
  x?: number
  y?: number
  action?: 'move' | 'attack' | 'move_and_fire'
}

/**
 * LLM 채팅 명령 처리
 */
export function useChatCommand() {
  const statusReportStore = useStatusReportStore()
  
  const isSending = ref(false)
  const error = ref<string | null>(null)
  
  /**
   * 채팅 메시지 전송
   */
  async function sendChatMessage(message: string): Promise<ChatResponse | null> {
    if (!message.trim()) {
      error.value = '메시지를 입력해주세요'
      return null
    }
    
    isSending.value = true
    error.value = null
    
    try {
      const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000'
      const api = new ApiService({ 
        baseURL: API_URL,
        debug: true  // 개발 중 디버그 활성화
      })
      
      const res = await api.post<ChatResponse>('/api/chat', {
        message: message
      })
      
      const result = res.data
      
      // command 타입이면 target 설정
      if (result.type === 'command' && result.x !== undefined && result.y !== undefined) {
        statusReportStore.setCommandTarget(result.x, result.y, 'defend')
        console.log(`목표 위치 설정: (${result.x}, ${result.y})`)
      }
      
      return result
      
    } catch (err) {
      error.value = `메시지 전송 실패: ${err instanceof Error ? err.message : '알 수 없는 오류'}`
      console.error('채팅 명령 실패:', err)
      return null
      
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