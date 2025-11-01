/**
 * SocketIO Service
 * 
 * Flask-SocketIO와 통신하는 클래스
 * Position, Detection, Fire 등 여러 WebSocket에서 재사용
 */

import { io, Socket } from 'socket.io-client'

export interface SocketIOConfig {
  url: string
  reconnection?: boolean      // 자동 재연결
  reconnectionDelay?: number  // 재연결 대기 시간 (ms)
  debug?: boolean             // 디버그 모드
}

export class SocketIOService {
  private socket: Socket | null = null
  private url: string
  private debug: boolean
  
  constructor(config: SocketIOConfig) {
    this.url = config.url
    this.debug = config.debug ?? false
  }
  
  /**
   * SocketIO 연결
   */
  connect(
    eventName: string,
    onMessage: (data: any) => void,
    onError?: (error: Error) => void,
    onDisconnect?: () => void
  ): void {
    try {
      // Socket.IO 클라이언트 생성
      this.socket = io(this.url, {
        reconnection: true,
        reconnectionDelay: 5000,
        transports: ['websocket', 'polling']  // WebSocket 우선, 실패 시 polling
      })
      
      // 연결 성공
      this.socket.on('connect', () => {
        if (this.debug) {
          console.log(`[SocketIO] 연결됨: ${this.url}`)
        }
      })
      
      // 메시지 수신
      this.socket.on(eventName, (data: any) => {
        if (this.debug) {
          console.log(`[SocketIO] 메시지 수신 (${eventName}):`, data)
        }
        onMessage(data)
      })
      
      // 에러 처리
      this.socket.on('connect_error', (error: Error) => {
        console.error(`[SocketIO] 연결 에러 (${this.url}):`, error)
        onError?.(error)
      })
      
      // 연결 해제
      this.socket.on('disconnect', (reason: string) => {
        if (this.debug) {
          console.log(`[SocketIO] 연결 종료 (${reason}): ${this.url}`)
        }
        onDisconnect?.()
      })
      
    } catch (error) {
      console.error('[SocketIO] 연결 실패:', error)
      onError?.(error as Error)
    }
  }
  
  /**
   * SocketIO 연결 해제
   */
  disconnect(): void {
    if (this.socket) {
      this.socket.disconnect()
      this.socket = null
      
      if (this.debug) {
        console.log(`[SocketIO] 수동 종료: ${this.url}`)
      }
    }
  }
  
  /**
   * 이벤트 전송
   */
  emit(eventName: string, data?: any): boolean {
    if (this.socket?.connected) {
      try {
        this.socket.emit(eventName, data)
        return true
      } catch (error) {
        console.error('[SocketIO] 전송 오류:', error)
        return false
      }
    } else {
      console.warn('[SocketIO] 연결되지 않았습니다')
      return false
    }
  }
  
  /**
   * 연결 상태 확인
   */
  isConnected(): boolean {
    return this.socket?.connected ?? false
  }
}