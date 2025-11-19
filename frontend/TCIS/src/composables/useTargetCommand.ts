import { ref } from 'vue'
import { usePositionStore } from '@/stores/position-store'
import { ApiService } from '@/services/api_service'

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
      const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
      const api = new ApiService({ baseURL: API_URL })
      const res = await api.post('/api/target', {
        x: target.x,
        y: target.y,
        timestamp: new Date().toISOString()
      })
      console.log('백엔드 응답:', res.data)
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