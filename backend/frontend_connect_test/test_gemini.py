"""
Gemini API 연결 테스트 - 최종 버전
"""

import os
import requests
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# API 키 가져오기
api_key = os.getenv('GEMINI_API_KEY')
if not api_key:
    print("ERROR: GEMINI_API_KEY가 .env 파일에 없습니다!")
    exit(1)

# 사용할 모델 (빠르고 무료인 flash 사용)
MODEL_NAME = "gemini-2.0-flash-001"

def call_gemini(message):
    """Gemini API 호출"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={api_key}"
    
    payload = {
        "contents": [{
            "parts": [{
                "text": message
            }]
        }]
    }
    
    response = requests.post(url, json=payload)
    
    if response.status_code == 200:
        result = response.json()
        return result['candidates'][0]['content']['parts'][0]['text']
    else:
        return f"에러: {response.text}"

# ============================================
# 테스트 시작
# ============================================

print("=" * 60)
print(f"Gemini API 연결 테스트 - {MODEL_NAME}")
print("=" * 60)

# 테스트 1: 간단한 응답
print("\n[테스트 1] 간단한 응답")
response = call_gemini("안녕하세요!")
print(f"응답: {response}")

# 테스트 2: 자연어 명령 파싱
print("\n[테스트 2] 자연어 명령 파싱")
test_messages = [
    "우측 상단으로 이동해",
    "지금 위치 어디야?",
    "오른쪽 위로 가면서 기동사격"
]

for msg in test_messages:
    print(f"\n입력: {msg}")
    response = call_gemini(msg)
    print(f"응답: {response[:100]}...")  # 처음 100자만 표시

print("\n" + "=" * 60)
print("테스트 완료! ✓")
print("=" * 60)