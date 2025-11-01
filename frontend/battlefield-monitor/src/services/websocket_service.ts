/**
 * WebSocket Service
 * 
 * WebSocket 연결을 관리하는 공통 클래스
 * Position, Detection, Fire 등 여러 WebSocket에서 재사용
 */

export interface WebSocketConfig {
  url: string
  reconnectInterval?: number  // 재연결 간격 (ms)
  debug?: boolean             // 디버그 모드
}

export class WebSocketService {
  private ws: WebSocket | null = null
  private url: string
  private reconnectInterval: number
  private debug: boolean
  private shouldReconnect: boolean = true
  private reconnectTimer: number | null = null
  
  constructor(config: WebSocketConfig) {
    this.url = config.url
    this.reconnectInterval = config.reconnectInterval ?? 5000
    this.debug = config.debug ?? false
  }
  
  /**
   * WebSocket 연결
   */
  connect(
    onMessage: (data: any) => void,
    onError?: (error: Event) => void,
    onClose?: () => void
  ): void {
    try {
      this.ws = new WebSocket(this.url)
      
      this.ws.onopen = () => {
        if (this.debug) {
          console.log(`[WebSocket] 연결됨: ${this.url}`)
        }
        
        // 재연결 타이머 초기화
        if (this.reconnectTimer) {
          clearTimeout(this.reconnectTimer)
          this.reconnectTimer = null
        }
      }
      
      this.ws.onmessage = (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data)
          onMessage(data)
        } catch (error) {
          console.error('WebSocket 메시지 파싱 오류:', error)
        }
      }
      
      this.ws.onerror = (error: Event) => {
        console.error(`[WebSocket] 오류 (${this.url}):`, error)
        onError?.(error)
      }
      
      this.ws.onclose = () => {
        if (this.debug) {
          console.log(`[WebSocket] 연결 종료: ${this.url}`)
        }
        
        onClose?.()
        
        // 자동 재연결
        if (this.shouldReconnect) {
          this.reconnectTimer = window.setTimeout(() => {
            if (this.debug) {
              console.log(`[WebSocket] 재연결 시도: ${this.url}`)
            }
            this.connect(onMessage, onError, onClose)
          }, this.reconnectInterval)
        }
      }
      
    } catch (error) {
      console.error('WebSocket 연결 실패:', error)
      onError?.(error as Event)
    }
  }
  
  /**
   * WebSocket 연결 해제
   */
  disconnect(): void {
    this.shouldReconnect = false
    
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
    
    if (this.debug) {
      console.log(`[WebSocket] 수동 종료: ${this.url}`)
    }
  }
  
  /**
   * 데이터 전송
   */
  send(data: any): boolean {
    if (this.ws?.readyState === WebSocket.OPEN) {
      try {
        this.ws.send(JSON.stringify(data))
        return true
      } catch (error) {
        console.error('WebSocket 전송 오류:', error)
        return false
      }
    } else {
      console.warn('WebSocket이 연결되지 않았습니다')
      return false
    }
  }
  
  /**
   * 연결 상태 확인
   */
  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN
  }
  
  /**
   * 연결 상태 (ReadyState)
   */
  getReadyState(): number | null {
    return this.ws?.readyState ?? null
  }
}