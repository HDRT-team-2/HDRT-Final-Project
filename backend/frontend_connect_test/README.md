# Frontend 연결 테스트 서버

Frontend 개발자가 Backend 없이도 독립적으로 개발/테스트할 수 있도록 Mock 서버 제공

## 설치

```bash
cd backend/frontend_connect_test
pip install -r requirements.txt
```

## 실행

```bash
python test_server.py
```

## 연결 정보

- **HTTP**: `http://localhost:5000`
- **WebSocket**: `ws://localhost:5000`

## 제공 API

### 1. POST `/api/target` (목표 위치 수신)

**요청:**
```json
{
  "x": 150.5,
  "y": 200.3,
  "timestamp": "2025-11-01T10:30:00"
}
```

**응답:**
```json
{
  "status": "success"
}
```

### 2. GET `/health` (서버 상태 확인)

**응답:**
```json
{
  "status": "ok",
  "message": "Mock server running"
}
```

## WebSocket 이벤트

### Detection (탐지)

**클라이언트 → 서버:**
- `start_detection`: 탐지 데이터 전송 시작
- `stop_detection`: 탐지 데이터 전송 중지

**서버 → 클라이언트:**
- `detection`: 탐지 데이터 (0.5초마다)
```json
{
  "type": "detection_update",
  "objects": [
    {
      "tracking_id": 1,
      "class_id": 1,
      "x": 120.5,
      "y": 80.3,
      "timestamp": "2025-11-01T10:30:00"
    }
  ]
}
```

### Position (위치)

**클라이언트 → 서버:**
- `start_position`: 위치 데이터 전송 시작
- `stop_position`: 위치 데이터 전송 중지

**서버 → 클라이언트:**
- `position`: 위치 데이터 (0.1초마다)
```json
{
  "type": "position_update",
  "x": 150.5,
  "y": 200.3,
  "angle": 45.2
}
```

### Fire (발포)

**클라이언트 → 서버:**
- `fire`: 발포 명령
```json
{
  "target_tracking_id": 5
}
```

**서버 → 클라이언트:**
- `fire_result`: 발포 결과
```json
{
  "type": "fire_event",
  "target_tracking_id": 5,
  "timestamp": "2025-11-01T10:30:00",
  "result": "success"
}
```

## 데이터 포맷

### 객체 클래스 ID
- `0`: PERSON (민간인)
- `1`: TANK (적 전차)
- `2`: CAR (민간 차량)
- `7`: TRUCK (민간 트럭)

### 좌표 범위
- X: 0 ~ 300
- Y: 0 ~ 300

## 실제 Backend 개발 시

### 삭제할 부분
1. `frontend_connect_test/` 폴더 전체
2. `mock/` 폴더의 모든 파일

### 참고할 부분
1. WebSocket 이벤트 구조
2. 데이터 포맷
3. API 엔드포인트 구조

### 교체 예시

**Mock (삭제):**
```python
data = generate_mock_detection()
```

**Real (추가):**
```python
data = get_detection_from_unity()  # 실제 Unity 데이터
```

## 주의사항

- 이 서버는 **테스트 전용**입니다
- 실제 배포 시 이 폴더 전체를 **반드시 삭제**하세요
- 데이터 포맷은 **절대 변경 금지**