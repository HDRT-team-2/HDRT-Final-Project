// 좌표 및 탱크 상태 관련 타입 정의
export interface Coordinate {
  x: number
  y: number
}

// 미션 타입 (백엔드와 통신용)
export type MissionType = 'defend' | 'attack_n_search'

// 백엔드 응답 미션 타입
export type BackendMissionType = 'attack' | 'search' | 'defence'

// 목표 위치를 나타내는 인터페이스
export interface TargetPosition extends Coordinate {
  mission: MissionType
}
// 내 탱크 위치 인터페이스
export interface TankPosition extends Coordinate {
  tank_id: string  // 탱크 식별자
}

// 백엔드에서 오는 내 Position 메시지 타입
export interface PositionMessage {
  type: 'position_update'
  tanks: TankPosition[]
}

// 백엔드에서 오는 Mission 메시지 타입
export interface MissionMessage {
  type: 'mission_update'
  mission: BackendMissionType
}
