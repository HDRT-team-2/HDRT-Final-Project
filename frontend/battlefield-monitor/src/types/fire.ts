// 발포 이벤트
export interface FireEvent {
  id: string // 고유 ID (프론트에서 생성)
  target_tracking_id: number // 발포 대상 tracking_id
  firedAt: Date // 발포 시간
  hitResult?: HitResult // 명중 결과 (나중에 업데이트)
}

// 명중 결과
export interface HitResult {
  hit: boolean // 명중 여부 (true: 명중, false: 미명중)
  hitAt: Date // 결과 확인 시간
}

// 백엔드에서 오는 발포 데이터
export interface FireResponse {
  target_tracking_id: number
  timestamp?: string
}

// 백엔드에서 오는 명중 결과 데이터
export interface HitResultResponse {
  target_tracking_id: number
  hit: boolean
  timestamp?: string
}

// Fire Store 상태
export interface FireState {
  fires: FireEvent[] // 모든 발포 이벤트
}