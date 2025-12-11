import { ref } from 'vue'
import { useStatusReportStore } from '@/stores/mission-status-store'
import { ApiService } from '@/services/api_service'
import type { BackendMissionType, MissionType } from '@/types/position'

// 목표 위치를 백엔드로 전송하고 이동 시작
export function useTargetCommand() {
  const statusReportStore = useStatusReportStore()
  
  const isSending = ref(false)
  const error = ref<string | null>(null)
  
  /**
   * 목표 위치 전송 (실제 백엔드)
   * TODO: 백엔드 연결 시 구현
   */
  async function sendTarget(): Promise<boolean> {
    const target = statusReportStore.commandTarget
    if (!target) {
      error.value = '목표 위치가 설정되지 않았습니다'
      return false
    }
    isSending.value = true
    error.value = null
    try {
      const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
      const api = new ApiService({ baseURL: API_URL })
      
      // 요청: 프론트 MissionType ('defense' | 'combat')
      // 응답: 백엔드 BackendMissionType ('combat' | 'search' | 'defense')
      console.log('목표 전송 요청:', target)
      const res = await api.post<{ x: number; y: number; mission: BackendMissionType }>('/api/target', {
        x: target.x,
        z: target.y,
        mission: target.mission as MissionType
      })
            
      // 응답 데이터로 mission status store 업데이트
      if (res.data) {
        
        console.log('목표 전송 성공:', res.data)
      }
      
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