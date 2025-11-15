"""
LLM 채팅 명령 처리 모듈
자연어 명령을 분석하여 JSON으로 반환
"""

import os
import json
import requests
from dotenv import load_dotenv

# .env 로드
load_dotenv()

# API 설정
API_KEY = os.getenv('GEMINI_API_KEY')
MODEL_NAME = "gemini-2.0-flash-001"
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={API_KEY}"

# 시스템 프롬프트
SYSTEM_PROMPT = """
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
- "오른쪽으로 가면서 사격" → {"type": "command", "x": 250, "y": 150, "action": "move_and_fire", "message": "네, 오른쪽으로 이동하며 기동사격하겠습니다"}  # ← Y좌표 수정
- "좌측 하단으로" → {"type": "command", "x": 40, "y": 40, "action": "move", "message": "네, 좌측 하단으로 이동하겠습니다"}  # ← 예시 추가
- "안녕" → {"type": "answer", "message": "안녕하세요! 명령을 기다리고 있습니다"}

반드시 JSON만 응답하세요. 다른 설명은 추가하지 마세요.
"""


def parse_chat_command(user_message):
    """
    사용자 메시지를 LLM으로 분석
    
    Args:
        user_message: 사용자 입력 메시지
        context: 현재 상태 정보 (선택적)
            {
                "targetPos": {"x": 100, "y": 200},
                "currentPos": {"x": 50, "y": 50}
            }
    
    Returns:
        dict: 파싱된 명령 JSON
    """
    
    # 컨텍스트가 있으면 프롬프트에 추가
    context = get_current_context()
    context_info = ""
    if context:
        context_info = f"\n\n현재 상태:\n{json.dumps(context, ensure_ascii=False, indent=2)}"
    
    # 최종 프롬프트
    full_prompt = f"{SYSTEM_PROMPT}{context_info}\n\n사용자 명령: {user_message}"
    
    # API 호출
    payload = {
        "contents": [{
            "parts": [{
                "text": full_prompt
            }]
        }]
    }
    
    try:
        response = requests.post(API_URL, json=payload, timeout=10)
        
        if response.status_code != 200:
            return {
                "type": "error",
                "message": "서버 오류가 발생했습니다."
            }
        
        result = response.json()
        llm_response = result['candidates'][0]['content']['parts'][0]['text']
        
        # JSON 파싱
        # LLM이 ```json ... ``` 로 감쌀 수 있으므로 제거
        llm_response = llm_response.strip()
        if llm_response.startswith('```json'):
            llm_response = llm_response[7:]
        if llm_response.startswith('```'):
            llm_response = llm_response[3:]
        if llm_response.endswith('```'):
            llm_response = llm_response[:-3]
        llm_response = llm_response.strip()
        
        parsed = json.loads(llm_response)
        return parsed
        
    except json.JSONDecodeError:
        return {
            "type": "error",
            "message": "응답 파싱 실패"
        }
    except Exception as e:
        print(f"LLM 호출 에러: {e}")
        return {
            "type": "error",
            "message": "처리 중 오류가 발생했습니다."
        }


def get_current_context():
    """
    Backend의 현재 상태 정보 가져오기
    mock_position에서 현재 위치와 목표 위치 조회
    """
    try:
        from mock import mock_position
        
        context = {
            "currentPos": {
                "x": round(mock_position.current_position['x'], 2),
                "y": round(mock_position.current_position['y'], 2)
            }
        }
        
        # 목표 위치가 설정되어 있으면 추가
        if mock_position.target_position:
            context["targetPos"] = {
                "x": round(mock_position.target_position[0], 2),
                "y": round(mock_position.target_position[1], 2)
            }
        
        return context
    except Exception as e:
        print(f"Context 로드 실패: {e}")
        # mock_position을 import 못하면 빈 context
        return {}
# ============================================
# 테스트 코드
# ============================================

if __name__ == "__main__":
    print("=" * 60)
    print("Chat Handler 테스트")
    print("=" * 60)

    try:
        from mock import mock_position 

        mock_position.current_position['x'] = 50.0
        mock_position.current_position['y'] = 100.0
        mock_position.set_target_position(200, 300)
        print(f"\n현재 테스트 상태: {get_current_context()}")
    except Exception as e:
        print(f"\n(mock_position 로드 실패: {e})")
    
    test_cases = [
        "우측 상단으로 이동해",
        "중앙 공격",
        "240, 180 으로 이동",
        "현재 설정된 위치로 이동",
        "현재 내 위치 어디야?",
        "안녕",
        "지금 목표 위치 어디야?"
    ]
    
    for msg in test_cases:
        print(f"\n입력: {msg}")
        result = parse_chat_command(msg)
        print(f"결과: {json.dumps(result, ensure_ascii=False, indent=2)}")