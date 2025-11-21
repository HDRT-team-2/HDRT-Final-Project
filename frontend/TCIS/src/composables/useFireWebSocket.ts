import { ref, onMounted, onUnmounted } from 'vue'
import { useFireStore } from '@/stores/fire-store'
import { SocketIOService } from '@/services/socketio_service'
import type { FireMessage, HitMessage } from '@/types/fire'

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
      'fire',
      // onMessage
      (data: FireMessage | HitMessage) => {
        // 발사 이벤트
        if (data.type === 'fire_event') {
          const fireData = data as FireMessage
          fireStore.addFire({
            target_tracking_id: fireData.target_tracking_id,
            ally_id: fireData.ally_id,
            class_id: fireData.class_id
          })
          console.log(`발사 수신: 아군 [${fireData.ally_id}] → 대상 [${fireData.target_tracking_id}] (${fireData.target_class_name})`)
        }
        // 명중 결과 이벤트
        else if (data.type === 'hit_result') {
          const hitData = data as HitMessage
          fireStore.updateFireResult(hitData.target_tracking_id, hitData.result)
          console.log(`명중 결과 수신: 대상 [${hitData.target_tracking_id}] - ${hitData.result}`)
        }
      },
      // onConnect
      () => {
        isConnected.value = true
        console.log('Fire WebSocket 연결됨')
      },
      // onDisconnect
      () => {
        isConnected.value = false
        console.log('Fire WebSocket 연결 끊김')
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