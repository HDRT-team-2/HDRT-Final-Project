import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import type { MissionReport, OperationMission } from '@/types/mission-status'
import type { BackendMissionType } from '@/types/position'

// 백엔드 미션을 한국어로 변환
function translateMission(backendMission: BackendMissionType): OperationMission {
  const missionMap: Record<BackendMissionType, OperationMission> = {
    'attack': '공격',
    'search': '수색',
    'defence': '방어'
  }
  return missionMap[backendMission]
}

// 미션별 기본 objective
function getDefaultObjective(mission: OperationMission): string {
  const objectiveMap: Record<OperationMission, string> = {
    '방어': '현재 전면전 개시 2일차로 아군, 적군간 대화력전이 실시되고 있는 상황.\n적 기갑부대는 남방한계선 북측 20km 지점까지 남하하였으며 아군은 공격개시선 남측 10km 지점에서 방어진지 구축 중.\n아군의 임무는 남하하는 적 기갑부대를 저지하고 현 위치를 고수하는 것.',
    '공격': '현재 전면전 개시 2일차로 아군, 적군간 대화력전이 실시되고 있는 상황.\n적 기갑부대는 남방한계선 북측 20km 지점까지 남하하였으며 아군은 공격개시선 남측 10km 지점에서 공격명령 대기중.\n아군의 임무는 남하하는 적 기갑부대를 격멸하고 목표지점을 확보하는 것.',
    '수색': '현재 전면전 개시 2일차로 아군, 적군간 대화력전이 실시되고 있는 상황.\n적 기갑부대는 남방한계선 북측 20km 지점까지 남하하였으며 정확한 위치 파악이 필요한 상황.\n아군의 임무는 지정된 지역을 수색하여 적의 위치와 병력을 파악하는 것.'
  }
  return objectiveMap[mission]
}

export const useStatusReportStore = defineStore('statusReport', () => {
  const missionReport = ref<MissionReport>({
    operationName: '천둥',
    commander: '신중건',
    mission: '방어',
    objective: '현재 전면전 개시 2일차로 아군, 적군간 대화력전이 실시되고 있는 상황.\n적 기갑부대는 남방한계선 북측 20km 지점까지 남하하였으며 아군은 공격개시선 남측 10km 지점에서 공격명령 대기중.\n아군의 임무는 남하하는 적 기갑부대를 격멸하고 목표지점인 00을 확보하는 것.'
  })

  // mission 변경 시 자동으로 objective 업데이트
  watch(() => missionReport.value.mission, (newMission) => {
    missionReport.value.objective = getDefaultObjective(newMission)
  })

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
  }

  const setObjective = (objective: string) => {
    missionReport.value.objective = objective
  }

  return {
    missionReport,
    updateStatusReport,
    setOperationName,
    setCommander,
    setMission,
    setMissionFromBackend,
    setObjective,
    translateMission
  }
})
