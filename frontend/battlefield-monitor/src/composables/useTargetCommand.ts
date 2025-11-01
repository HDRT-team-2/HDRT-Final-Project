import { ref } from 'vue'
import { usePositionStore } from '@/stores/position'

// 목표 위치를 백엔드로 전송하고 이동 시작
export function useTargetCommand() {
  const positionStore = usePositionStore()
  
  const isSending = ref(false)
  const error = ref<string | null>(null)
  
  /**
   * 목표 위치 전송 (실제 백엔드)
   * TODO: 백엔드 연결 시 구현
   */
  async function sendTarget(): Promise<boolean> {
    const target = positionStore.target
    
    if (!target) {
      error.value = '목표 위치가 설정되지 않았습니다'
      return false
    }
    
    isSending.value = true
    error.value = null
    
    try {
      // #TODO: 실제 백엔드 URL
      const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
      
      const response = await fetch(`${API_URL}/api/target`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          x: target.x,
          y: target.y,
          timestamp: new Date().toISOString()
        })
      })
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      
      console.log('목표 전송 성공:', target)
      return true
      
    } catch (err) {
      error.value = `목표 전송 실패: ${err instanceof Error ? err.message : '알 수 없는 오류'}`
      console.error('목표 전송 실패:', err)
      return false
      
    } finally {
      isSending.value = false
    }
  }
  
  return {
    isSending,
    error,
    sendTarget
  }
}

/**
 * 🎮 테스트용: Mock Target Command
 * WebSocket에 목표 전달
 */
export function useMockTargetCommand(mockWebSocket: any) {
  const positionStore = usePositionStore()
  
  const isSending = ref(false)
  const error = ref<string | null>(null)
  
  /**
   * Mock: 목표 전송 + WebSocket 시작
   */
  async function sendTarget(): Promise<boolean> {
    const target = positionStore.target
    
    if (!target) {
      error.value = '목표 위치가 설정되지 않았습니다'
      return false
    }
    
    isSending.value = true
    error.value = null
    
    try {
      // 가짜 네트워크 지연
      await new Promise(resolve => setTimeout(resolve, 300))
      
      console.log('🎮 Mock 목표 전송:', target)
      
      // WebSocket 시작: 해당 목표로 이동
      mockWebSocket.startMovingTo(target.x, target.y)
      
      isSending.value = false
      return true
      
    } catch (err) {
      error.value = '목표 전송 실패'
      console.error('목표 전송 실패:', err)
      isSending.value = false
      return false
    }
  }
  
  return {
    isSending,
    error,
    sendTarget
  }
}