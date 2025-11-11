// 발포 이벤트
export interface FireEvent {
  id: string // 고유 ID (프론트에서 생성)
  target_tracking_id: number // 발포 대상 tracking_id
  firedAt: Date // 발포 시간
}

// 백엔드에서 오는 발포 데이터
export interface FireResponse {
  target_tracking_id: number
  timestamp?: string
}


// Fire Store 상태
export interface FireState {
  fires: FireEvent[] // 모든 발포 이벤트
}