import { ref, onMounted, onUnmounted } from 'vue'
import { usePositionStore } from '@/stores/position'
import type { TankPosition } from '@/types/position'

/**
 * WebSocket으로 현재 위치 수신 (실시간)
 * - 단방향: Backend → Frontend
 * - 계속 수신하여 Store 업데이트
 */
export function usePositionWebSocket() {
  const positionStore = usePositionStore()
  
  const isConnected = ref(false)
  const ws = ref<WebSocket | null>(null)
  
  // WebSocket 연결
  function connect() {
    // #TODO: 백엔드 URL 설정
    const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws/position'
    
    try {
      ws.value = new WebSocket(WS_URL)
      
      ws.value.onopen = () => {
        console.log('Position WebSocket 연결됨')
        isConnected.value = true
      }
      
      ws.value.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          
          // 백엔드에서 보내는 메시지 형식:
          // { type: 'position_update', x: 150, y: 200, angle: 45 }
          if (data.type === 'position_update') {
            const position: TankPosition = {
              x: data.x,
              y: data.y,
              angle: data.angle
            }
            
            // Store 업데이트 → 자동으로 PositionInfo 컴포넌트 반영
            positionStore.updateCurrentPosition(position)
          }
        } catch (error) {
          console.error('WebSocket 메시지 파싱 에러:', error)
        }
      }
      
      ws.value.onerror = (error) => {
        console.error('WebSocket 에러:', error)
        isConnected.value = false
      }
      
      ws.value.onclose = () => {
        console.log('WebSocket 연결 종료')
        isConnected.value = false
        
        // 자동 재연결 (5초 후)
        setTimeout(() => {
          console.log('재연결 시도...')
          connect()
        }, 5000)
      }
      
    } catch (error) {
      console.error('WebSocket 연결 실패:', error)
      isConnected.value = false
    }
  }

  // WebSocket 연결 해제
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
    console.log('Position WebSocket 대기 중')
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
 * 🎮 테스트용: Mock WebSocket
 * 동적으로 목표 위치를 설정하여 이동
 */
export function useMockPositionWebSocket() {
  const positionStore = usePositionStore()
  
  let intervalId: number | null = null
  let currentX = 0
  let currentY = 0
  let targetX = 0
  let targetY = 0
  const speed = 1.806 // 0.1초당 이동 거리 (65km/h)
  
  /**
   * 목표 위치로 이동 시작
   */
  function startMovingTo(x: number, y: number) {
    // 이전 이동 중지
    stop()
    
    // 새로운 목표 설정
    targetX = x
    targetY = y
    
    // 시작 위치 초기화
    currentX = 0
    currentY = 0
    
    console.log(`🎮 Mock WebSocket 시작: (0,0) → (${targetX}, ${targetY})`)
    
    // 0.1초마다 업데이트
    intervalId = window.setInterval(() => {
      const dx = targetX - currentX
      const dy = targetY - currentY
      const distance = Math.sqrt(dx * dx + dy * dy)
      
      if (distance < speed) {
        // 목표 도착
        currentX = targetX
        currentY = targetY
        console.log('🏁 목표 도착!')
        stop()
      } else {
        // 계속 이동
        const ratio = speed / distance
        currentX += dx * ratio
        currentY += dy * ratio
      }
      
      // 각도 계산 (이동 방향)
      const angle = Math.atan2(dx, -dy) * (180 / Math.PI)
      
      const mockPosition: TankPosition = {
        x: currentX,
        y: currentY,
        angle: angle >= 0 ? angle : angle + 360
      }
      
      positionStore.updateCurrentPosition(mockPosition)
      console.log(`📍 위치: (${currentX.toFixed(1)}, ${currentY.toFixed(1)})`)
    }, 100)
  }
  
  function stop() {
    if (intervalId !== null) {
      clearInterval(intervalId)
      intervalId = null
      console.log('🛑 Mock WebSocket 중지')
    }
  }
  
  return { 
    startMovingTo,  // ✨ 이제 외부에서 목표 설정 가능
    stop 
  }
}