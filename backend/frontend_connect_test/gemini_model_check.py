"""
Gemini API - 사용 가능한 모델 확인
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

print("=" * 60)
print("사용 가능한 Gemini 모델 확인")
print("=" * 60)

# 모델 목록 조회
list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"

try:
    response = requests.get(list_url)
    
    if response.status_code == 200:
        models = response.json()
        print("\n사용 가능한 모델:")
        for model in models.get('models', []):
            name = model.get('name', '')
            methods = model.get('supportedGenerationMethods', [])
            if 'generateContent' in methods:
                print(f"✓ {name}")
    else:
        print(f"에러: {response.text}")
        exit(1)
        
except Exception as e:
    print(f"예외 발생: {e}")
    exit(1)

print("\n" + "=" * 60)
print("이제 위 모델 중 하나를 선택해서 테스트합니다")
print("=" * 60)

# 일반적으로 사용 가능한 모델들 시도
test_models = [
    "gemini-1.5-flash",
    "gemini-1.5-flash-latest", 
    "gemini-1.5-pro",
    "gemini-1.5-pro-latest",
    "gemini-pro",
    "models/gemini-1.5-flash",
    "models/gemini-pro"
]

print("\n각 모델로 테스트 중...\n")

for model_name in test_models:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    
    payload = {
        "contents": [{
            "parts": [{
                "text": "안녕"
            }]
        }]
    }
    
    response = requests.post(url, json=payload)
    
    if response.status_code == 200:
        print(f"✓ 성공: {model_name}")
        result = response.json()
        answer = result['candidates'][0]['content']['parts'][0]['text']
        print(f"  응답: {answer[:50]}...")
        print(f"\n이 모델을 사용하세요: {model_name}")
        break
    else:
        print(f"✗ 실패: {model_name}")