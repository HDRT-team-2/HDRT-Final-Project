/**
 * LLM Service - Frontend에서 직접 Gemini API 호출
 */

export interface LLMCommandResult {
  type: 'command' | 'answer' | 'error'
  message: string
  x?: number
  y?: number
  action?: 'move' | 'attack' | 'move_and_fire'
}

// Gemini API 설정
const API_KEY = import.meta.env.VITE_GEMINI_API_KEY
const MODEL_NAME = 'gemini-2.0-flash-001'
const API_URL = `https://generativelanguage.googleapis.com/v1beta/models/${MODEL_NAME}:generateContent?key=${API_KEY}`

// 시스템 프롬프트
const SYSTEM_PROMPT = `
당신은 군사 로봇 제어 시스템의 AI 어시스턴트입니다.
사용자의 자연어 명령을 분석하여 JSON 형식으로 응답해야 합니다.

화면 좌표 기준:
- 화면 크기: 300x300
- 좌측 하단: (0, 0)      
- 우측 상단: (300, 300)  
- 중앙: (150, 150)
- 좌측 상단: (0, 300)    
- 우측 하단: (300, 0)    

응답 형식은 반드시 다음 중 하나여야 합니다:

1. 이동/공격 명령인 경우:
{
  "type": "command",
  "x": 좌표값,
  "y": 좌표값,
  "action": "move" 또는 "attack" 또는 "move_and_fire",
  "message": "사용자에게 보여줄 응답 메시지"
}

2. 질문인 경우:
{
  "type": "answer",
  "message": "질문에 대한 답변"
}

3. 이해할 수 없는 경우:
{
  "type": "error",
  "message": "명령을 이해할 수 없습니다. 다시 말씀해주세요."
}

예시:
- "우측 상단으로 이동" → {"type": "command", "x": 260, "y": 260, "action": "move", "message": "네, (260, 260)으로 이동하겠습니다"}
- "중앙 공격" → {"type": "command", "x": 150, "y": 150, "action": "attack", "message": "네, 중앙 (150, 150)을 공격하겠습니다"}
- "오른쪽으로 가면서 사격" → {"type": "command", "x": 250, "y": 150, "action": "move_and_fire", "message": "네, 오른쪽으로 이동하며 기동사격하겠습니다"}
- "좌측 하단으로" → {"type": "command", "x": 40, "y": 40, "action": "move", "message": "네, 좌측 하단으로 이동하겠습니다"}
- "안녕" → {"type": "answer", "message": "안녕하세요! 명령을 기다리고 있습니다"}

반드시 JSON만 응답하세요. 다른 설명은 추가하지 마세요.
`

/**
 * 현재 컨텍스트 정보 구성
 */
function buildContextInfo(currentPos?: { x: number; y: number }, targetPos?: { x: number; y: number }): string {
  if (!currentPos && !targetPos) {
    return ''
  }

  const context: any = {}
  
  if (currentPos) {
    context.currentPos = {
      x: Math.round(currentPos.x * 100) / 100,
      y: Math.round(currentPos.y * 100) / 100
    }
  }
  
  if (targetPos) {
    context.targetPos = {
      x: Math.round(targetPos.x * 100) / 100,
      y: Math.round(targetPos.y * 100) / 100
    }
  }

  return `\n\n현재 상태:\n${JSON.stringify(context, null, 2)}`
}

/**
 * LLM으로 자연어 명령 분석
 */
export async function parseCommandWithLLM(
  userMessage: string,
  context?: {
    currentPos?: { x: number; y: number }
    targetPos?: { x: number; y: number }
  }
): Promise<LLMCommandResult> {
  
  // API 키 확인
  if (!API_KEY) {
    console.error('VITE_GEMINI_API_KEY가 설정되지 않았습니다')
    return {
      type: 'error',
      message: 'API 키가 설정되지 않았습니다. 환경 변수를 확인해주세요.'
    }
  }

  // 컨텍스트 정보 추가
  const contextInfo = buildContextInfo(context?.currentPos, context?.targetPos)
  const fullPrompt = `${SYSTEM_PROMPT}${contextInfo}\n\n사용자 명령: ${userMessage}`

  // API 호출 페이로드
  const payload = {
    contents: [{
      parts: [{
        text: fullPrompt
      }]
    }]
  }

  try {
    const response = await fetch(API_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    })

    if (!response.ok) {
      console.error('Gemini API 오류:', response.status, response.statusText)
      return {
        type: 'error',
        message: 'AI 서비스 오류가 발생했습니다.'
      }
    }

    const result = await response.json()
    let llmResponse = result.candidates?.[0]?.content?.parts?.[0]?.text

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
