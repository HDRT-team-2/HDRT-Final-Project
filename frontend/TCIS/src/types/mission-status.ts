export type OperationMission = '방어' | '수색' | '공격'

export interface MissionReport {
  operationName: string
  commander: string
  mission: OperationMission
  objective: string
}
