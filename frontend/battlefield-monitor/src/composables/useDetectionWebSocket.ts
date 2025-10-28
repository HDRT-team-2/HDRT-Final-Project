import { ref, onMounted, onUnmounted } from 'vue'
import { useDetectionStore } from '@/stores/detection'
import type { DetectionResponse } from '@/types/detection'

/**
 * WebSocket으로 탐지 객체 수신 (실시간)
 * - 단방향: Backend → Frontend
 * - 계속 수신하여 Store 업데이트
 */
export function useDetectionWebSocket() {
  const detectionStore = useDetectionStore()
  
  const isConnected = ref(false)
  const ws = ref<WebSocket | null>(null)
  
  /**
   * WebSocket 연결
   */
  function connect() {
    // #TODO: 백엔드 URL 설정
    const WS_URL = import.meta.env.VITE_DETECTION_WS_URL || 'ws://localhost:8000/ws/detection'
    
    try {
      ws.value = new WebSocket(WS_URL)
      
      ws.value.onopen = () => {
        console.log('Detection WebSocket 연결됨')
        isConnected.value = true
      }
      
      ws.value.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          
          // 백엔드에서 보내는 메시지 형식:
          // { type: 'detection_update', objects: [...] }
          if (data.type === 'detection_update' && Array.isArray(data.objects)) {
            detectionStore.updateObjects(data.objects)
            console.log(`탐지 수신: ${data.objects.length}개 객체`)
          }
        } catch (error) {
          console.error('Detection WebSocket 메시지 파싱 에러:', error)
        }
      }
      
      ws.value.onerror = (error) => {
        console.error('Detection WebSocket 에러:', error)
        isConnected.value = false
      }
      
      ws.value.onclose = () => {
        console.log('Detection WebSocket 연결 종료')
        isConnected.value = false
        
        // 자동 재연결 (5초 후)
        setTimeout(() => {
          console.log('Detection WebSocket 재연결 시도...')
          connect()
        }, 5000)
      }
      
    } catch (error) {
      console.error('Detection WebSocket 연결 실패:', error)
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
    console.log('Detection WebSocket 대기 중')
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
 * 테스트용: Mock Detection WebSocket
 * 랜덤 탐지 객체 생성
 */
export function useMockDetectionWebSocket() {
  const detectionStore = useDetectionStore()
  
  let intervalId: number | null = null
  let trackingIdCounter = 1
  
  /**
   * 랜덤 탐지 데이터 생성
   */
  function generateMockDetections(): DetectionResponse[] {
    const mockData: DetectionResponse[] = []
    
    // 랜덤으로 1~3개의 객체 생성
    const count = Math.floor(Math.random() * 3) + 1
    
    for (let i = 0; i < count; i++) {
      // 랜덤 클래스 (0: person, 1: tank, 2: car, 7: truck)
      const classIds = [0, 1, 2, 7]
      const randomIndex = Math.floor(Math.random() * classIds.length)
      const randomClassId = classIds[randomIndex] as number
      
      mockData.push({
        tracking_id: trackingIdCounter++,
        class_id: randomClassId,
        x: Math.random() * 300,
        y: Math.random() * 300,
        timestamp: new Date().toISOString()
      })
    }
    
    return mockData
  }
  
  /**
   * Mock WebSocket 시작
   */
  function start() {
    console.log('🎮 Mock Detection WebSocket 시작')
    
    // 2초마다 랜덤 탐지 데이터 생성
    intervalId = window.setInterval(() => {
      const mockDetections = generateMockDetections()
      detectionStore.updateObjects(mockDetections)
      
      console.log(`🔍 Mock 탐지: ${mockDetections.length}개 객체 생성`)
    }, 2000)
  }
  
  /**
   * Mock WebSocket 중지
   */
  function stop() {
    if (intervalId !== null) {
      clearInterval(intervalId)
      intervalId = null
      console.log('🛑 Mock Detection WebSocket 중지')
    }
  }
  
  return {
    start,
    stop
  }
}