import { ref, onMounted, onUnmounted } from 'vue'
import { usePositionStore } from '@/stores/position-store'
import { SocketIOService } from '@/services/socketio_service'
import type { PositionMessage } from '@/types/position'

/**
 * SocketIO로 현재 위치 수신 (실시간)
 * - 단방향: Backend → Frontend
 * - 계속 수신하여 Store 업데이트
 */
export function usePositionWebSocket() {
  const positionStore = usePositionStore()
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
      'position',
      // onMessage
      (data: PositionMessage) => {
        // 백엔드에서 보내는 메시지 형식:
        // { type: 'position_update', tanks: [{ tank_id: '17TK-101', x: 150, y: 200 }, ...] }
        if (data.type === 'position_update' && Array.isArray(data.tanks)) {
          data.tanks.forEach(tank => {
            positionStore.updateTankPosition(tank)
          })
          console.log(`위치 수신: ${data.tanks.length}개 탱크`)
        }
      },
      // onError
      (error) => {
        console.error('Position SocketIO 에러:', error)
        isConnected.value = false
      },
      // onDisconnect
      () => {
        isConnected.value = false
      }
    )
    
    isConnected.value = true
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
    console.log('Position SocketIO 연결 시작')
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