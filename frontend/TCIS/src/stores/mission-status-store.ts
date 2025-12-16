import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { MissionReport, OperationMission } from '@/types/mission-status'
import type { BackendMissionType } from '@/types/position'

// 백엔드 미션을 한국어로 변환
function translateMission(backendMission: BackendMissionType): OperationMission {
  const missionMap: Record<BackendMissionType, OperationMission> = {
    'combat': '공격',
    'search': '수색',
    'defense': '방어'
  }
  return missionMap[backendMission]
}

export const useStatusReportStore = defineStore('statusReport', () => {
  const missionReport = ref<MissionReport>({
    operationName: '천둥',
    commander: '신중건',
    mission: '',
    objective: '적 기갑여단이 철원평야를 가로지르며 고속 돌파를 시도하고 있다.\n만약 이 돌파를 허용하면, 주요 도로와 철도 모두 적에게 점령되어 군 보급 작전에 심각한 제한 사항이 발생한다.\n00전차대대는 백마고지 남측 능선에서 적의 돌파를 차단하라.',
    targetPosition: null
  })
  
  // 백엔드에서 임무를 받았는지 여부
  const hasMissionReceived = ref(false)

  // 프론트에서 명령한 목표 (API 전송용)
  const commandTarget = ref<{ x: number; y: number; mission: import('@/types/position').MissionType } | null>(null)

  const updateStatusReport = (data: Partial<MissionReport>) => {
    missionReport.value = { ...missionReport.value, ...data }
  }

  const setOperationName = (name: string) => {
    missionReport.value.operationName = name
  }

  const setCommander = (commander: string) => {
    missionReport.value.commander = commander
  }

  const setMission = (mission: OperationMission) => {
    missionReport.value.mission = mission
  }

  const setMissionFromBackend = (backendMission: BackendMissionType) => {
    const koreanMission = translateMission(backendMission)
    missionReport.value.mission = koreanMission
    hasMissionReceived.value = true
  }

  const setObjective = (objective: string) => {
    missionReport.value.objective = objective
  }

  const setTargetPosition = (x: number, y: number) => {
    missionReport.value.targetPosition = { x, y }
  }

  const setCommandTarget = (x: number, y: number, mission: import('@/types/position').MissionType) => {
    commandTarget.value = { x, y, mission }
  }

  const clearCommandTarget = () => {
    commandTarget.value = null
  }

  return {
    missionReport,
    commandTarget,
    hasMissionReceived,
    updateStatusReport,
    setOperationName,
    setCommander,
    setMission,
    setMissionFromBackend,
    setObjective,
    setTargetPosition,
    setCommandTarget,
    clearCommandTarget,
    translateMission
  }
})
