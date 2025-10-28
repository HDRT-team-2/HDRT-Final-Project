import { ref, onMounted, onUnmounted } from 'vue'
import { useFireStore } from '@/stores/fire'
import type { FireResponse, HitResultResponse } from '@/types/fire'

/**
 * WebSocket으로 발포/명중 이벤트 수신 (실시간)
 * - 단방향: Backend → Frontend
 * - 발포 이벤트 + 명중 결과 이벤트 수신
 */
export function useFireWebSocket() {
  const fireStore = useFireStore()
  
  const isConnected = ref(false)
  const ws = ref<WebSocket | null>(null)
  
  /**
   * WebSocket 연결
   */
  function connect() {
    // 🔧 TODO: 백엔드 URL 설정
    const WS_URL = import.meta.env.VITE_FIRE_WS_URL || 'ws://localhost:8000/ws/fire'
    
    try {
      ws.value = new WebSocket(WS_URL)
      
      ws.value.onopen = () => {
        console.log('Fire WebSocket 연결됨')
        isConnected.value = true
      }
      
      ws.value.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          
          // 발포 이벤트
          if (data.type === 'fire') {
            fireStore.addFire(data as FireResponse)
            console.log(`발포 수신: 대상 [${data.target_tracking_id}]`)
          }
          
          // 명중 결과 이벤트
          else if (data.type === 'hit_result') {
            fireStore.updateHitResult(data as HitResultResponse)
            const result = data.hit ? '🎯 명중' : '❌ 미명중'
            console.log(`${result} 수신: 대상 [${data.target_tracking_id}]`)
          }
        } catch (error) {
          console.error('Fire WebSocket 메시지 파싱 에러:', error)
        }
      }
      
      ws.value.onerror = (error) => {
        console.error('Fire WebSocket 에러:', error)
        isConnected.value = false
      }
      
      ws.value.onclose = () => {
        console.log('Fire WebSocket 연결 종료')
        isConnected.value = false
        
        // 자동 재연결 (5초 후)
        setTimeout(() => {
          console.log('Fire WebSocket 재연결 시도...')
          connect()
        }, 5000)
      }
      
    } catch (error) {
      console.error('Fire WebSocket 연결 실패:', error)
      isConnected.value = false
    }
  }
  
  /**
   * WebSocket 연결 해제
   */
  function disconnect() {
    if (ws.value) {
      ws.value.close()
      ws.value = null
      isConnected.value = false
    }
  }
  
  // 컴포넌트 마운트 시 자동 연결
  onMounted(() => {
    // #TODO: 백엔드 준비되면 주석 해제
    // connect()
    console.log('Fire WebSocket 대기 중')
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

/**
 * 🎮 테스트용: Mock Fire WebSocket
 * Detection에서 적 전차 발견 시 자동 발포
 */
export function useMockFireWebSocket() {
  const fireStore = useFireStore()
  
  /**
   * 적 전차 발견 시 발포
   * @param tankTrackingId 발견된 적 전차의 tracking_id
   */
  function fireAtTank(tankTrackingId: number) {
    const fireData: FireResponse = {
      target_tracking_id: tankTrackingId,
      timestamp: new Date().toISOString()
    }
    
    fireStore.addFire(fireData)
    console.log(`🔫 발포: 적 전차 [${tankTrackingId}]`)
    
    // 1초 후 명중 결과 (98% 명중률)
    setTimeout(() => {
      const hit = Math.random() < 0.98 // 98% 명중
      
      const hitResultData: HitResultResponse = {
        target_tracking_id: tankTrackingId,
        hit: hit,
        timestamp: new Date().toISOString()
      }
      
      fireStore.updateHitResult(hitResultData)
    }, 1000)
  }
  
  return {
    fireAtTank
  }
}