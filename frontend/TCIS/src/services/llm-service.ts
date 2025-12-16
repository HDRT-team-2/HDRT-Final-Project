/**
 * LLM Service - Frontend에서 직접 Gemini API 호출
 */

import type { DetectedObject } from '@/types/detection'
import type { TankPosition, MissionType } from '@/types/position'
import type { FireEvent } from '@/types/fire'

export interface LLMCommandResult {
  type: 'command' | 'answer' | 'error' | 'relative_command' | 'config' | 'multi'
  message: string
  x?: number
  y?: number
  mission?: 'defense' | 'combat' | 'search'
  // 상대적 명령용 필드
  target?: 'closest_enemy' | 'farthest_enemy' | 'center_enemy' | 'topmost_enemy' | 'bottommost_enemy' | 'leftmost_enemy' | 'rightmost_enemy'
  targetType?: 'tank' | 'infantry' | 'any'
  // 설정 변경용 필드
  operationName?: string
  commander?: string
  // 다중 명령용 필드
  commands?: Array<{
    type: 'command' | 'relative_command' | 'config'
    message?: string
    x?: number
    y?: number
    mission?: 'defense' | 'combat'
    target?: string
    targetType?: string
    operationName?: string
    commander?: string
  }>
}

export interface LLMContext {
  currentMission?: MissionType
  detectedObjects?: DetectedObject[]
  myTanks?: TankPosition[]
  targetPosition?: { x: number; y: number }
  fireHistory?: FireEvent[]
  operationName?: string
  commander?: string
}

// OpenAI API 설정
const API_KEY = import.meta.env.VITE_OPENAI_API_KEY
const MODEL_NAME = 'gpt-4o-mini' // 저렴하고 빠른 모델
const API_URL = '/api/llm' // Vite 프록시를 통해 OpenAI API 호출

// Rate Limiting (요청 제한)
let lastRequestTime = 0
const MIN_REQUEST_INTERVAL = 1000 // 1초 (OpenAI는 더 여유로움)

// 시스템 프롬프트 (간결하고 원칙 중심)
const SYSTEM_PROMPT = `군사 AI. 존댓말 사용. JSON만 출력.

중요 규칙:
- 숫자,숫자 패턴 보이면 무조건 command (config 아님!)
- "지시자" = "지휘관"
- 좌표 없고 작전명/지휘관만 있으면 config

타입 구분:
1. 명확한 좌표(x,y) + 임무어 → type:"command" (최우선!)
   - 좌표가 있으면 무조건 command (config 아님)
   - mission: combat(공격), defense(방어), search(수색)
   예: "100,200 공격" → {"type":"command","x":100,"y":200,"mission":"combat","message":"목표 설정"}
   예: "300,300으로 방어" → {"type":"command","x":300,"y":300,"mission":"defense","message":"방어 위치 설정"}

2. 좌표 없이 공격/방어/수색 명령 → type:"relative_command"
   - target: closest_enemy(기본), farthest_enemy, topmost_enemy, bottommost_enemy, leftmost_enemy, rightmost_enemy, center_enemy
   - targetType: tank(전차), infantry(보병), any(기본)
   - mission: combat, defense, search
   예시:
   - "적 공격" → {"type":"relative_command","target":"closest_enemy","targetType":"any","mission":"combat"}
   - "전차 공격" → {"type":"relative_command","target":"closest_enemy","targetType":"tank","mission":"combat"}
   - "가장 먼 적" → {"type":"relative_command","target":"farthest_enemy","targetType":"any","mission":"combat"}

3. 질문 → type:"answer"
   - 컨텍스트 정보만 사용. 없으면 "정보 없습니다"
   - "적 몇", "적 갯수", "적 개수" → 살아있는 적 (적전차N, 적보병N)
   - "제거한 적", "사망한 적", "죽은 적" → 제거한 적 (제거한전차N, 제거한보병N)
   - "거리", "몇 떨어져", "얼마나 떨어져" → 내위치와 적 좌표로 거리 계산 가능. sqrt((x1-x2)^2 + (y1-y2)^2) 공식 사용
   예: {"type":"answer","message":"적 전차 2대 (100,50), (120,60)입니다"}
   예: {"type":"answer","message":"제거한 적 전차 3대, 보병 5명입니다"}
   예: {"type":"answer","message":"내 위치 (134,165)에서 적까지 거리: 1번째 적 53.9, 2번째 적 26.2, 3번째 적 9.1입니다"}

4. 작전명/지휘관 설정/변경 → type:"config"
   - "작전명", "지휘관", "지시자" (지시자=지휘관) 키워드 포함
   - 좌표(x,y)가 있으면 config 아님! command 우선
   - "나는 Y", "지시자는 Y", "지휘관 Y" → commander=Y
   예시:
   - "작전명을 천둥으로" → {"type":"config","operationName":"천둥","message":"작전명을 천둥으로 변경했습니다"}
   - "지휘관 홍길동" → {"type":"config","commander":"홍길동","message":"지휘관을 홍길동으로 변경했습니다"}
   - "나는 권다솔 작전 지시자다" → {"type":"config","commander":"권다솔","message":"지휘관을 권다솔로 변경했습니다"}
   - "작전명은 번개 나는 권다솔" → {"type":"config","operationName":"번개","commander":"권다솔","message":"작전명을 번개, 지휘관을 권다솔로 변경했습니다"}
   - "작전명은 X 123,456 공격" → config 우선! {"type":"config","operationName":"X",...} (좌표는 무시)
   - "작전명은 번개 나는 권다솔" → {"type":"config","operationName":"번개","commander":"권다솔","message":"작전명을 번개, 지휘관을 권다솔로 변경했습니다"}

5. 여러 명령 동시 입력 → type:"multi"
   - commands 배열에 순서대로 명령 나열
   예: "작전명은 번개 나는 권다솔이다. 123,456으로 공격하라" → 
   {"type":"multi","message":"작전명 변경 및 공격 명령","commands":[{"type":"config","operationName":"번개","commander":"권다솔"},{"type":"command","x":123,"y":456,"mission":"combat"}]}
- 추측 금지. 컨텍스트에 없으면 "정보 없습니다"
- 존댓말 필수`

/**
 * 전장 컨텍스트 정보 구성 (토큰 절약)
 */
function buildContextInfo(context?: LLMContext): string {
  if (!context) return ''

  const parts: string[] = []

  // 작전명
  if (context.operationName) {
    parts.push(`작전명:${context.operationName}`)
  }
  
  // 지휘관
  if (context.commander) {
    parts.push(`지휘관:${context.commander}`)
  }
  
  // 현재 임무 (한국어로 변환)
  let missionKorean = '미정'
  if (context.currentMission) {
    missionKorean = context.currentMission === 'defense' ? '방어' : context.currentMission === 'combat' ? '공격' : '미정'
    parts.push(`임무:${missionKorean}`)
  }

  // 내 전차 (첫 번째만)
  if (context.myTanks && context.myTanks.length > 0) {
    const t = context.myTanks[0]
    parts.push(`내위치:(${Math.round(t.x)},${Math.round(t.y)})`)
  }

  // 목표 위치 (있으면, 임무에 따라 이름 변경)
  if (context.targetPosition) {
    const targetLabel = missionKorean === '방어' ? '방어위치' : missionKorean === '공격' ? '공격위치' : '목표'
    parts.push(`${targetLabel}:(${Math.round(context.targetPosition.x)},${Math.round(context.targetPosition.y)})`)
  }

  // 탐지된 객체 (상세 정보 포함)
  if (context.detectedObjects && context.detectedObjects.length > 0) {
    const objs = context.detectedObjects
    const enemyTanks = objs.filter(obj => (obj.class_name === 'tank' || obj.class_name === 'tank_around') && obj.alive)
    const enemyInfantry = objs.filter(obj => (obj.class_name === 'human' || obj.class_name === 'human_around') && obj.alive)
    const deadEnemyTanks = objs.filter(obj => (obj.class_name === 'tank' || obj.class_name === 'tank_around') && !obj.alive)
    const deadEnemyInfantry = objs.filter(obj => (obj.class_name === 'human' || obj.class_name === 'human_around') && !obj.alive)
    const obstacles = objs.filter(obj => ['rock_small', 'rock_large', 'wall', 'mine', 'other'].includes(obj.class_name))
    console.log('[LLM Context] 전체 객체:', objs.length, '장애물:', obstacles.length, obstacles.map(o => o.class_name))
    const vehicles = objs.filter(obj => ['car', 'truck'].includes(obj.class_name))
    
    const summary: string[] = []
    if (enemyTanks.length > 0) {
      console.log('[LLM Context] 적 전차:', enemyTanks.map(t => ({ id: t.tracking_id, pos: t.position })))
      const positions = enemyTanks.map(t => `(${Math.round(t.position.x)},${Math.round(t.position.y)})`).join(',')
      summary.push(`적전차${enemyTanks.length}[${positions}]`)
    }
    if (enemyInfantry.length > 0) {
      const positions = enemyInfantry.map(t => `(${Math.round(t.position.x)},${Math.round(t.position.y)})`).join(',')
      summary.push(`적보병${enemyInfantry.length}[${positions}]`)
    }
    if (deadEnemyTanks.length > 0) {
      summary.push(`제거한전차${deadEnemyTanks.length}`)
    }
    if (deadEnemyInfantry.length > 0) {
      summary.push(`제거한보병${deadEnemyInfantry.length}`)
    }
    if (obstacles.length > 0) summary.push(`장애물:${obstacles.length}개`)
    if (vehicles.length > 0) summary.push(`차량:${vehicles.length}개`)
    
    parts.push(`탐지:${summary.join(',')}`)
  }

  // 사격 이력 (요약만)
  if (context.fireHistory && context.fireHistory.length > 0) {
    const hits = context.fireHistory.filter(f => f.result === 'hit').length
    parts.push(`사격:${context.fireHistory.length}회(명중${hits})`)
  }

  return parts.length > 0 ? `\n상황:${parts.join(',')}` : ''
}

/**
 * LLM으로 자연어 명령 분석
 */
export async function parseCommandWithLLM(
  userMessage: string,
  context?: LLMContext
): Promise<LLMCommandResult> {
  
  // API 키 확인
  if (!API_KEY) {
    console.error('VITE_OPENAI_API_KEY가 설정되지 않았습니다')
    return {
      type: 'error',
      message: 'OpenAI API 키가 설정되지 않았습니다. 환경 변수를 확인해주세요.'
    }
  }
  
  // 디버깅: 사용 중인 API 키 확인
  console.log('사용 중인 API 키:', API_KEY?.substring(0, 20) + '...')

  // Rate Limiting 체크
  const now = Date.now()
  const timeSinceLastRequest = now - lastRequestTime
  if (timeSinceLastRequest < MIN_REQUEST_INTERVAL) {
    const waitTime = Math.ceil((MIN_REQUEST_INTERVAL - timeSinceLastRequest) / 1000)
    return {
      type: 'error',
      message: `요청이 너무 빠릅니다. ${waitTime}초 후에 다시 시도해주세요.`
    }
  }
  lastRequestTime = now

  // 질문에 따라 필요한 컨텍스트만 선택적으로 추가
  const needsContext = /임무|탐지|전차|보병|위치|목표|사격|명중|적|아군|객체|장애물|바위|지뢰|차량/i.test(userMessage)
  const contextInfo = needsContext ? buildContextInfo(context) : ''
  
  console.log('컨텍스트 포함 여부:', needsContext, '| 질문:', userMessage)
  
  const fullPrompt = `${SYSTEM_PROMPT}${contextInfo}\n질문:${userMessage}`

  // OpenAI API 호출 페이로드
  const payload = {
    model: MODEL_NAME,
    messages: [
      { role: 'system', content: SYSTEM_PROMPT + contextInfo },
      { role: 'user', content: `질문:${userMessage}` }
    ],
    temperature: 0.3,
    max_tokens: 500
  }

  try {
    const response = await fetch(API_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${API_KEY}`
      },
      body: JSON.stringify(payload)
    })

    if (!response.ok) {
      const errorText = await response.text()
      console.error('OpenAI API 오류:', response.status, response.statusText, errorText)
      
      if (response.status === 429) {
        return {
          type: 'error',
          message: 'API 요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요.'
        }
      }
      
      if (response.status === 401) {
        return {
          type: 'error',
          message: 'API 키가 유효하지 않습니다. 키를 확인해주세요.'
        }
      }
      
      return {
        type: 'error',
        message: `AI 서비스 오류 (${response.status}): API 키를 확인해주세요.`
      }
    }

    const result = await response.json()
    let llmResponse = result.choices?.[0]?.message?.content

    if (!llmResponse) {
      return {
        type: 'error',
        message: 'AI 응답을 받을 수 없습니다.'
      }
    }

    // JSON 코드 블록 제거
    llmResponse = llmResponse.trim()
    if (llmResponse.startsWith('```json')) {
      llmResponse = llmResponse.substring(7)
    }
    if (llmResponse.startsWith('```')) {
      llmResponse = llmResponse.substring(3)
    }
    if (llmResponse.endsWith('```')) {
      llmResponse = llmResponse.substring(0, llmResponse.length - 3)
    }
    llmResponse = llmResponse.trim()

    // JSON 파싱
    const parsed = JSON.parse(llmResponse) as LLMCommandResult
    return parsed

  } catch (error) {
    console.error('LLM 명령 파싱 실패:', error)
    
    if (error instanceof SyntaxError) {
      return {
        type: 'error',
        message: 'AI 응답 형식이 올바르지 않습니다.'
      }
    }

    return {
      type: 'error',
      message: '명령 처리 중 오류가 발생했습니다.'
    }
  }
}
