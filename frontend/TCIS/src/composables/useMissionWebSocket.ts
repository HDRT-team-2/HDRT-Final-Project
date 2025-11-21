import { ref, onMounted, onUnmounted } from 'vue'
import { useStatusReportStore } from '@/stores/mission-status-store'
import { SocketIOService } from '@/services/socketio_service'
import type { MissionMessage } from '@/types/position'

/**
 * SocketIO로 미션 상태 수신 (실시간)
 * - 단방향: Backend → Frontend
 * - 계속 수신하여 mission-status-store 업데이트
 */
export function useMissionWebSocket() {
  const statusReportStore = useStatusReportStore()
  const isConnected = ref(false)
  
  // Backend URL 설정
  const BACKEND_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000'
  
  // SocketIOService 인스턴스 생성
  const service = new SocketIOService({
    url: BACKEND_URL,
    debug: true
  })
  
  /**
   * SocketIO 연결
   */
  function connect() {
    service.connect(
      // eventName
      'mission',
      // onMessage
      (data: MissionMessage) => {
        // 백엔드에서 보내는 메시지 형식:
        // { type: 'mission_update', mission: 'attack' | 'search' | 'defence' }
        if (data.type === 'mission_update' && data.mission) {
          // mission-status-store의 공통 함수 사용 (한국어 변환 포함)
          statusReportStore.setMissionFromBackend(data.mission)
          console.log(`미션 수신: ${data.mission}`)
        }
      },
      // onConnect
      () => {
        isConnected.value = true
        console.log('Mission WebSocket 연결됨')
      },
      // onDisconnect
      () => {
        isConnected.value = false
        console.log('Mission WebSocket 연결 끊김')
      }
    )
  }
  
  /**
   * SocketIO 연결 해제
   */
  function disconnect() {
    service.disconnect()
    isConnected.value = false
  }
  
  // 컴포넌트 마운트 시 자동 연결
  onMounted(() => {
    connect()
  })
  
  // 컴포넌트 언마운트 시 자동 연결 해제
  onUnmounted(() => {
    disconnect()
  })
  
  return {
    isConnected,
    connect,
    disconnect
  }
}
