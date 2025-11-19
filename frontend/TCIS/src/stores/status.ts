import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { StatusReport, OperationStatus } from '@/types/status'

export const useStatusReportStore = defineStore('statusReport', () => {
  const statusReport = ref<StatusReport>({
    operationName: '천둥',
    commander: '신중건',
    status: '방어',
    objective: '현재 전면전 개시 2일차로 아군, 적군간 대화력전이 실시되고 있는 상황.\n적 기갑부대는 남방한계선 북측 20km 지점까지 남하하였으며 아군은 공격개시선 남측 10km 지점에서 공격명령 대기중.\n아군의 임무는 남하하는 적 기갑부대를 격멸하고 목표지점인 00을 확보하는 것.'
  })

  const updateStatusReport = (data: Partial<StatusReport>) => {
    statusReport.value = { ...statusReport.value, ...data }
  }

  const setOperationName = (name: string) => {
    statusReport.value.operationName = name
  }

  const setCommander = (commander: string) => {
    statusReport.value.commander = commander
  }

  const setStatus = (status: OperationStatus) => {
    statusReport.value.status = status
  }

  const setObjective = (objective: string) => {
    statusReport.value.objective = objective
  }

  return {
    statusReport,
    updateStatusReport,
    setOperationName,
    setCommander,
    setStatus,
    setObjective
  }
})
