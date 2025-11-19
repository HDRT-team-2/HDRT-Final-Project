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
  className?: string // 탐지된 객체 클래스 (detection) 또는 발포 대상 클래스 (fire)
  pos?: {
    x: number
    y: number
  }
  time?: Date // 프론트엔드에서 생성
}

// Situation Store 상태
export interface SituationState {
  events: SituationEvent[]
  maxEvents: number // 최대 이벤트 개수
}