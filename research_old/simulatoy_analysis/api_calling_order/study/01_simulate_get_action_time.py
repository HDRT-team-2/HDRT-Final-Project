"""
목적 : 함수실행 시 행동(get_action) 기능의 출력 시간 ms까지 측정되게 만드는 코드
"""
from flask import Flask, request, jsonify
import os
import torch
from ultralytics import YOLO
from datetime import datetime

# Flask 앱 생성
app = Flask(__name__)

# YOLOv8 nano 모델 로드 (COCO 80클래스 사전학습 가중치)
# 서버 시작 시 1회 로드 → 요청마다 재사용(추론 지연 감소)
model = YOLO('yolov8n.pt')

# 시뮬레이터에 순차적으로 보낼 샘플 액션 시퀀스(큐처럼 pop(0)으로 사용)
combined_commands = [
    {
        "moveWS": {"command": "W", "weight": 1.0},   # 전/후 축: 전진(W) 강도 1.0
        "moveAD": {"command": "D", "weight": 1.0},   # 좌/우 축: 우측(D) 강도 1.0
        "turretQE": {"command": "Q", "weight": 0.7}, # 포탑 좌우: Q(좌) 강도 0.7
        "turretRF": {"command": "R", "weight": 0.5}, # 포각 상하: R(상) 강도 0.5
        "fire": False                                # 사격 여부
    },
    {
        "moveWS": {"command": "W", "weight": 0.6},
        "moveAD": {"command": "A", "weight": 0.4},
        "turretQE": {"command": "E", "weight": 0.8},
        "turretRF": {"command": "R", "weight": 0.3},
        "fire": True
    },
    {
        "moveWS": {"command": "W", "weight": 0.5},
        "moveAD": {"command": "", "weight": 0.0},
        "turretQE": {"command": "E", "weight": 0.4},
        "turretRF": {"command": "R", "weight": 0.6},
        "fire": False
    },
    {
        "moveWS": {"command": "W", "weight": 0.3},
        "moveAD": {"command": "D", "weight": 0.3},
        "turretQE": {"command": "E", "weight": 0.5},
        "turretRF": {"command": "R", "weight": 0.7},
        "fire": True
    },
    {
        "moveWS": {"command": "W", "weight": 1.0},
        "moveAD": {"command": "", "weight": 0.0},
        "turretQE": {"command": "E", "weight": 0.5},
        "turretRF": {"command": "R", "weight": 0.5},
        "fire": False
    },
    {
        "moveWS": {"command": "W", "weight": 0.8},
        "moveAD": {"command": "A", "weight": 0.6},
        "turretQE": {"command": "E", "weight": 0.9},
        "turretRF": {"command": "R", "weight": 0.2},
        "fire": True
    },
    {
        "moveWS": {"command": "W", "weight": 1.0},
        "moveAD": {"command": "D", "weight": 1.0},
        "turretQE": {"command": "E", "weight": 1.0},
        "turretRF": {"command": "R", "weight": 1.0},
        "fire": True
    },
    {
        "moveWS": {"command": "W", "weight": 0.2},
        "moveAD": {"command": "A", "weight": 0.9},
        "turretQE": {"command": "", "weight": 0.0},
        "turretRF": {"command": "R", "weight": 0.9},
        "fire": False
    },
    {
        "moveWS": {"command": "S", "weight": 0.4},
        "moveAD": {"command": "D", "weight": 0.4},
        "turretQE": {"command": "E", "weight": 0.6},
        "turretRF": {"command": "F", "weight": 0.6},
        "fire": True
    },
    {
        "moveWS": {"command": "W", "weight": 0.8},
        "moveAD": {"command": "", "weight": 0.0},
        "turretQE": {"command": "Q", "weight": 0.5},
        "turretRF": {"command": "", "weight": 0.0},
        "fire": False
    },
    {
        "moveWS": {"command": "STOP", "weight": 1.0},
        "moveAD": {"command": "", "weight": 0.0},
        "turretQE": {"command": "", "weight": 0.0},
        "turretRF": {"command": "", "weight": 0.0},
        "fire": True
    },
    {
        "moveWS": {"command": "S", "weight": 0.2},
        "moveAD": {"command": "A", "weight": 0.2},
        "turretQE": {"command": "E", "weight": 0.2},
        "turretRF": {"command": "F", "weight": 0.2},
        "fire": False
    }
]


@app.route('/detect', methods=['POST'])
def detect():
    """
    업로드된 이미지를 YOLO로 추론해 객체를 감지한 뒤,
    타깃 클래스만 필터링하여 JSON으로 반환.
    """
    image = request.files.get('image')                  # multipart/form-data의 파일 키: 'image'
    if not image:
        return jsonify({"error": "No image received"}), 400

    # 간단 구현: 디스크에 저장 후 경로로 추론
    # (실서비스: UUID 파일명/메모리 추론 권장 — 동시성 충돌 방지)
    image_path = 'temp_image.jpg'
    image.save(image_path)

    # YOLO 추론 실행
    results = model(image_path)

    # 결과의 바운딩박스 텐서를 numpy로 변환
    # 포맷: [x1, y1, x2, y2, conf, class_id]
    detections = results[0].boxes.data.cpu().numpy()

    # 타깃 클래스 매핑
    #   COCO 기준: 0=person, 2=car, 7=truck. (15는 bench)
    #   현재 15→"rock"은 COCO와 불일치 → rock이 필요하면 커스텀 모델 필요
    target_classes = {0: "person", 2: "car", 7: "truck", 15: "rock"}

    filtered_results = []
    for box in detections:
        class_id = int(box[5])
        if class_id in target_classes:
            filtered_results.append({
                'className': target_classes[class_id],           # 감지된 클래스명
                'bbox': [float(coord) for coord in box[:4]],     # [x1,y1,x2,y2]
                'confidence': float(box[4]),                     # 신뢰도(0~1)
                'color': '#00FF00',                              # 프론트 표시용(예시)
                'filled': False,                                 # 프론트 옵션(예시)
                'updateBoxWhileMoving': False                    # 프론트 옵션(예시)
            })

    return jsonify(filtered_results)

@app.route('/info', methods=['POST'])
def info():
    """
    시뮬레이터 측 상태 정보 수신(시간, 스코어 등).
    현재는 유효성 검사 후 성공 응답만 반환.
    """
    data = request.get_json(force=True)                 # Content-Type 상관없이 JSON 파싱
    if not data:
        return jsonify({"error": "No JSON received"}), 400

    # 예시: 특정 시간 경과 시 자동 제어 신호를 주고 싶다면 아래와 같이 활용 가능
    # if data.get("time", 0) > 15:
    #     return jsonify({"status": "success", "control": "pause"})

    return jsonify({"status": "success", "control": ""})

@app.route('/get_action', methods=['POST'])
def get_action():
    """
    시뮬레이터가 보낸 현재 상태(position, turret)를 참고해 다음 행동 명령을 반환.
    - 현재 구현: combined_commands에서 하나씩 꺼내서 반환(없으면 기본 STOP 명령).
    - 아래에 추가한 블록은 특정 명령이 '정확히 W/A/Q/R = 1.0'일 때
      그 시점의 호출 시간을 ms까지 로그로 남김(행동 이벤트 타임스탬프용).
    """
    data = request.get_json(force=True)

    # 상태 파싱(현재는 로깅만; 의사결정에는 미사용)
    position = data.get("position", {})
    turret = data.get("turret", {})
    pos_x = position.get("x", 0)
    pos_y = position.get("y", 0)
    pos_z = position.get("z", 0)
    turret_x = turret.get("x", 0)
    turret_y = turret.get("y", 0)

    print(f"📨 Position received: x={pos_x}, y={pos_y}, z={pos_z}")
    print(f"🎯 Turret received: x={turret_x}, y={turret_y}")

    # 큐에 남은 동작이 있으면 pop(0)으로 하나 소비, 없으면 기본값
    if combined_commands:
        command = combined_commands.pop(0)
    else:
        command = {
            "moveWS": {"command": "", "weight": 0.0},
            "moveAD": {"command": "", "weight": 0.0},
            "turretQE": {"command": "", "weight": 0.0},
            "turretRF": {"command": "", "weight": 0.0},
            "fire": False
        }

    # ↓↓↓ 아래 블록은 ‘특정 축/포탑 명령이 강도 1.0으로 들어온 순간’을 ms로 로깅
    #     (의도: 행동 이벤트의 발생 시각을 고해상도로 남기기 위함)
    if command["moveWS"]["command"].upper() == "W" and command["moveWS"]["weight"] == 1.0:
        now = datetime.now()
        current_time = now.strftime("%Y-%m-%d %H:%M:%S.") + f"{int(now.microsecond / 1000):03d}"
        print(f"⏰ 전차가 이동 (W=1.0) - 호출 시간: {current_time}")

    if command["moveAD"]["command"].upper() == "A" and command["moveAD"]["weight"] == 1.0:
        now = datetime.now()
        current_time = now.strftime("%Y-%m-%d %H:%M:%S.") + f"{int(now.microsecond / 1000):03d}"
        print(f"⏰ 전차가 이동 (A=1.0) - 호출 시간: {current_time}")

    if command["turretQE"]["command"].upper() == "Q" and command["turretQE"]["weight"] == 1.0:
        now = datetime.now()
        current_time = now.strftime("%Y-%m-%d %H:%M:%S.") + f"{int(now.microsecond / 1000):03d}"
        print(f"⏰ 전차가 이동 (Q=1.0) - 호출 시간: {current_time}")

    if command["turretRF"]["command"].upper() == "R" and command["turretRF"]["weight"] == 1.0:
        now = datetime.now()
        current_time = now.strftime("%Y-%m-%d %H:%M:%S.") + f"{int(now.microsecond / 1000):03d}"
        print(f"⏰ 전차가 이동 (R=1.0) - 호출 시간: {current_time}")

    print("🔁 Sent Combined Action:", command)
    return jsonify(command)

@app.route('/update_bullet', methods=['POST'])
def update_bullet():
    """
    포탄 명중/충돌 리포트 수신 — 현재는 콘솔 로그만 남기고 OK 응답.
    (발사 간격 측정/통계가 필요하면 여기서 타임스탬프를 기록·차분하도록 확장 가능)
    """
    data = request.get_json()
    if not data:
        return jsonify({"status": "ERROR", "message": "Invalid request data"}), 400

    print(f"💥 Bullet Impact at X={data.get('x')}, Y={data.get('y')}, Z={data.get('z')}, Target={data.get('hit')}")
    return jsonify({"status": "OK", "message": "Bullet impact data received"})

@app.route('/set_destination', methods=['POST'])
def set_destination():
    """
    이동 목표 좌표를 "x,y,z" 문자열로 받아 float으로 파싱 후 확인 응답.
    형식 불일치 시 400 반환.
    """
    data = request.get_json()
    if not data or "destination" not in data:
        return jsonify({"status": "ERROR", "message": "Missing destination data"}), 400

    try:
        x, y, z = map(float, data["destination"].split(","))
        print(f"🎯 Destination set to: x={x}, y={y}, z={z}")
        return jsonify({"status": "OK", "destination": {"x": x, "y": y, "z": z}})
    except Exception as e:
        return jsonify({"status": "ERROR", "message": f"Invalid format: {str(e)}"}), 400

@app.route('/update_obstacle', methods=['POST'])
def update_obstacle():
    """
    장애물 정보 수신 — 현재는 수신 데이터 콘솔 출력 후 OK 응답.
    """
    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': 'No data received'}), 400

    print("🪨 Obstacle Data:", data)
    return jsonify({'status': 'success', 'message': 'Obstacle data received'})

@app.route('/collision', methods=['POST']) 
def collision():
    """
    충돌 이벤트 수신(오브젝트명 + 좌표) — 콘솔 로그 후 OK 응답.
    """
    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': 'No collision data received'}), 400

    object_name = data.get('objectName')
    position = data.get('position', {})
    x = position.get('x')
    y = position.get('y')
    z = position.get('z')

    print(f"💥 Collision Detected - Object: {object_name}, Position: ({x}, {y}, {z})")
    return jsonify({'status': 'success', 'message': 'Collision data received'})

# 에피소드 시작 시 호출되는 초기 설정
@app.route('/init', methods=['GET'])
def init():
    """
    시뮬레이터 초기화 설정값 전달.
    """
    config = {
        "startMode": "start",  # 시작 모드: "start" or "pause"
        "blStartX": 60,  "blStartY": 10, "blStartZ": 27.23,  # Blue 시작 좌표
        "rdStartX": 59,  "rdStartY": 10, "rdStartZ": 280,    # Red 시작 좌표
        "trackingMode": True,   # 추적 모드
        "detectMode": False,  
        "logMode": False,
        "enemyTracking": False,
        "saveSnapshot": False,
        "saveLog": False,
        "saveLidarData": False,
        "lux": 30000            # 조도(예시)
    }
    print("🛠️ Initialization config sent via /init:", config)
    return jsonify(config)

@app.route('/start', methods=['GET'])
def start():
    """시뮬레이션 시작 신호 — 간단 확인 응답."""
    print("🚀 /start command received")
    return jsonify({"control": ""})

if __name__ == '__main__':
    # 개발용 내장 서버 실행 (외부 접속 허용, 포트 5000)
    # 운영 환경에서는 Gunicorn/Uvicorn 등 WSGI/ASGI 서버 사용 권장
    app.run(host='0.0.0.0', port=5000)
