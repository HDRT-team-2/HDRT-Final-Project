import { ref, onMounted, onUnmounted } from 'vue'
import { useDetectionStore } from '@/stores/detection-store'
import { SocketIOService } from '@/services/socketio_service'
import type { DetectionMessage } from '@/types/detection'

/**
 * SocketIO로 탐지 객체 수신 (실시간)
 * - 단방향: Backend → Frontend
 * - 계속 수신하여 Store 업데이트
 */
export function useDetectionWebSocket() {
  const detectionStore = useDetectionStore()
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
      'detection',
      // onMessage
      (data: DetectionMessage) => {
        // 백엔드에서 보내는 메시지 형식:
        // { type: 'detection_update', 
        //   object: {  
        //     "tracking_id": 0001, 
        //     "class_id": 5, 
        //     "x": 123.445, 
        //     "z": 67.849,
        //     "alive": true 
        //   }
        // }
        if (data.type === 'detection_update' && data.object) {
          detectionStore.updateObject(data.object)
          console.log(`탐지 수신: [${data.object.tracking_id}] ${data.object.class_id}`)
        }
      },
      // onError
      (error) => {
        console.error('Detection SocketIO 에러:', error)
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
    console.log('Detection SocketIO 연결 시작')
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