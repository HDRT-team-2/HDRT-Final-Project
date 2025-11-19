export type OperationStatus = '방어' | '수색' | '공격'

export interface StatusReport {
  operationName: string
  commander: string
  status: OperationStatus
  objective: string
}
