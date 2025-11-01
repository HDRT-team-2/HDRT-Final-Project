import { ref, onMounted, onUnmounted } from 'vue'
import { useFireStore } from '@/stores/fire'
import { SocketIOService } from '@/services/socketio_service'
import type { FireResponse, HitResultResponse } from '@/types/fire'

/**
 * SocketIO로 발포/명중 이벤트 수신 (실시간)
 * - 단방향: Backend → Frontend
 * - 발포 이벤트 + 명중 결과 이벤트 수신
 */
export function useFireWebSocket() {
  const fireStore = useFireStore()
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
      'fire_result',
      // onMessage
      (data: any) => {
        // 발포 이벤트
        if (data.type === 'fire_event') {
          fireStore.addFire(data as FireResponse)
          console.log(`발포 수신: 대상 [${data.target_tracking_id}]`)
        }
        
      },
      // onError
      (error) => {
        console.error('Fire SocketIO 에러:', error)
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
    console.log('Fire SocketIO 연결 시작')
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