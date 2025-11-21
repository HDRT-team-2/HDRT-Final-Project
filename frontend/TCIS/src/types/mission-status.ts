export type OperationMission = '방어' | '수색' | '공격'

export interface MissionReport {
  operationName: string
  commander: string
  mission: OperationMission
  objective: string
  targetPosition: { x: number; y: number } | null // 목표 위치 (백엔드에서 확정된 위치)
}
