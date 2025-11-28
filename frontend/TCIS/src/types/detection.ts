import type { Coordinate } from './position'

//객체 클래스 ID
export enum ObjectClassId {
  Other = 0,
  Car2 = 1,
  Car3 = 2,
  Car4 = 3,
  Human1 = 4,
  Tank1 = 5,
  Rock1 = 6,
  Rock2 = 7,
  Mine1 = 8,
  Wall2 = 9,
  Wall2X10 = 10,
}

//객체 클래스 이름
export type ObjectClassName = 'tank' | 'car' | 'truck' | 'other' | 'human' | 'rock_small' | 'rock_large' | 'mine' | 'wall'

//클래스 ID → 이름 매핑
export const CLASS_ID_TO_NAME: Record<number, ObjectClassName> = {
  [ObjectClassId.Other]: 'other',
  [ObjectClassId.Car2]: 'car',
  [ObjectClassId.Car3]: 'car',
  [ObjectClassId.Car4]: 'car',
  [ObjectClassId.Human1]: 'human',
  [ObjectClassId.Tank1]: 'tank',
  [ObjectClassId.Rock1]: 'rock_small',
  [ObjectClassId.Rock2]: 'rock_large',
  [ObjectClassId.Mine1]: 'mine',
  [ObjectClassId.Wall2]: 'wall',
  [ObjectClassId.Wall2X10]: 'wall',
}

//클래스 이름 한글

export const CLASS_NAME_KR: Record<ObjectClassName, string> = {
  human: '보병',
  tank: '전차',
  car: '차량',
  truck: '트럭',
  other: '기타',
  rock_small: '작은 바위',
  rock_large: '큰 바위',
  mine: '지뢰',
  wall: '벽'
}

// 프론트에서 사용할 형태
export interface DetectedObject {
  tracking_id: number // 백엔드에서 추적 중인 고유 ID
  class_id: number // 백엔드에서 오는 클래스 ID
  class_name: ObjectClassName // 변환된 클래스 이름
  position: Coordinate // 위치
  time: Date // 발견 시간
  alive: boolean // 생존 여부
}

// 백엔드에서 오는 원본 데이터
export interface DetectionResponse {
    tracking_id: number
    class_id: number
    x: number
    z: number,
    alive: boolean,
}

// 백엔드에서 오는 Detection 메시지 타입
export interface DetectionMessage {
  type: 'detection_update'
  object: DetectionResponse
}

// Detection Store 상태
export interface DetectionState {
  objects: DetectedObject[] // 탐지된 모든 객체
}