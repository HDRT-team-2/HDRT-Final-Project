import type { Coordinate } from './position'

//객체 클래스 ID
export enum ObjectClassId {
  PERSON = 0,    // 민간인
  TANK = 1,      // 적 전차
  CAR = 2,       // 민간 차량
  TRUCK = 7      // 민간 트럭
}

//객체 클래스 이름
export type ObjectClassName = 'person' | 'tank' | 'car' | 'truck'

//클래스 ID → 이름 매핑
export const CLASS_ID_TO_NAME: Record<number, ObjectClassName> = {
  [ObjectClassId.PERSON]: 'person',
  [ObjectClassId.TANK]: 'tank',
  [ObjectClassId.CAR]: 'car',
  [ObjectClassId.TRUCK]: 'truck'
}

//클래스 이름 한글

export const CLASS_NAME_KR: Record<ObjectClassName, string> = {
  person: '사람',
  tank: '적 전차',
  car: '차량',
  truck: '트럭'
}

// 탐지된 객체
export interface DetectedObject {
  tracking_id: number // 백엔드에서 추적 중인 고유 ID
  class_id: number // 백엔드에서 오는 클래스 ID
  class_name: ObjectClassName // 변환된 클래스 이름
  position: Coordinate // 위치
  detectedAt: Date // 발견 시간
  lastUpdated: Date // 마지막 업데이트 시간
  distance?: number // 거리 (계산됨)
  angle?: number // 각도 (계산됨)
}

// 백엔드에서 오는 원본 데이터
export interface DetectionResponse {
    tracking_id: number
    class_id: number
    x: number
    y: number
    timestamp?: string
}

// Detection Store 상태
export interface DetectionState {
  objects: DetectedObject[] // 탐지된 모든 객체
}