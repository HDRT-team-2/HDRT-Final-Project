/**
 * LLM Service - Frontend에서 직접 Gemini API 호출
 */

import type { DetectedObject } from '@/types/detection'
import type { TankPosition, MissionType } from '@/types/position'
import type { FireEvent } from '@/types/fire'

export interface LLMCommandResult {
  type: 'command' | 'answer' | 'error'
  message: string
  x?: number
  y?: number
  mission?: 'defense' | 'combat'
}

export interface LLMContext {
  currentMission?: MissionType
  detectedObjects?: DetectedObject[]
  myTanks?: TankPosition[]
  targetPosition?: { x: number; y: number }
  fireHistory?: FireEvent[]
}

// OpenAI API 설정
const API_KEY = import.meta.env.VITE_OPENAI_API_KEY
const MODEL_NAME = 'gpt-4o-mini' // 저렴하고 빠른 모델
const API_URL = '/api/llm' // Vite 프록시를 통해 OpenAI API 호출

// Rate Limiting (요청 제한)
let lastRequestTime = 0
const MIN_REQUEST_INTERVAL = 1000 // 1초 (OpenAI는 더 여유로움)

// 시스템 프롬프트 (토큰 절약을 위해 최소화)
const SYSTEM_PROMPT = `군사 로봇 AI. 좌표(0-300), 임무(defense/combat).

응답 형식:
1. 임무변경: {"type":"command","x":150,"y":200,"mission":"defense","message":"답변"}
2. 질문: {"type":"answer","message":"답변"}
3. 오류: {"type":"error","message":"오류"}

JSON만 출력.`

/**
 * 전장 컨텍스트 정보 구성 (토큰 절약)
 */
function buildContextInfo(context?: LLMContext): string {
  if (!context) return ''

  const parts: string[] = []

  // 현재 임무
  if (context.currentMission) {
    parts.push(`임무:${context.currentMission}`)
  }

  // 내 전차 (첫 번째만)
  if (context.myTanks && context.myTanks.length > 0) {
    const t = context.myTanks[0]
    parts.push(`내위치:(${Math.round(t.x)},${Math.round(t.y)})`)
  }

  // 목표 위치
  if (context.targetPosition) {
    parts.push(`목표:(${Math.round(context.targetPosition.x)},${Math.round(context.targetPosition.y)})`)
  }

  // 탐지된 객체 (요약만)
  if (context.detectedObjects && context.detectedObjects.length > 0) {
    const tanks = context.detectedObjects.filter(obj => obj.class_name === 'tank' || obj.class_name === 'tank_around')
    const humans = context.detectedObjects.filter(obj => obj.class_name === 'human' || obj.class_name === 'human_around')
    parts.push(`탐지:전체${context.detectedObjects.length}(전차${tanks.length},보병${humans.length})`)
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
  const needsContext = /임무|탐지|전차|보병|위치|목표|사격|명중|적|아군|객체/i.test(userMessage)
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
