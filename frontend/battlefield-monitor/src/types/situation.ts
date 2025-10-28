// 상황 이벤트 타입
export type SituationEventType = 
  | 'detection'  // 객체 탐지
  | 'fire'       // 발포
  | 'hit'        // 명중
  | 'miss'       // 미명중

// 상황 이벤트
export interface SituationEvent {
  id: string
  type: SituationEventType
  time: Date
  tracking_id?: number // 관련된 객체/발포 tracking_id
  className?: string // 탐지된 객체 클래스 (detection일 때)
  message: string // 표시할 메시지
}

// Situation Store 상태
export interface SituationState {
  events: SituationEvent[]
  maxEvents: number // 최대 이벤트 개수
}