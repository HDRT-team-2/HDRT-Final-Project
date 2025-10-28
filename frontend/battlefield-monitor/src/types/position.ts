// 좌표 및 탱크 상태 관련 타입 정의
export interface Coordinate {
  x: number
  y: number
}
// 내 탱크 위치를 나타내는 인터페이스
export interface TankPosition extends Coordinate {
  angle: number
}
// 목표 위치를 나타내는 인터페이스
export interface TargetPosition extends Coordinate {
  setAt?: Date
}
// 내 탱크 상태를 나타내는 인터페이스
export interface TankStatus {
  speed: number
  isMoving: boolean
  health: number
}
