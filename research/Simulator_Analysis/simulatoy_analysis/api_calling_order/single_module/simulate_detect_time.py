"""
목적 : 함수실행 시 탐지(detect) 기능의 출력 시간 ms까지 측정되게 만드는 코드
"""
from flask import Flask, request, jsonify
import os
import torch
from ultralytics import YOLO
from datetime import datetime

# Flask 애플리케이션 생성
app = Flask(__name__)

# YOLOv8 Nano 모델 로드(사전학습: COCO 80 클래스) — 서버 시작 시 1회 로드 후 재사용
model = YOLO('yolov8n.pt')

# 시뮬레이터에 차례대로 보낼 샘플 액션 목록(큐처럼 pop(0)으로 하나씩 소비)
combined_commands = [
    {
        "moveWS": {"command": "W", "weight": 1.0},   # 전/후 이동축: 전진(W), 강도 1.0
        "moveAD": {"command": "D", "weight": 1.0},   # 좌/우 이동축: 우측(D), 강도 1.0
        "turretQE": {"command": "Q", "weight": 0.7}, # 포탑 좌우: Q(좌), 강도 0.7
        "turretRF": {"command": "R", "weight": 0.5}, # 포각 상하: R(상향), 강도 0.5
        "fire": False                                # 사격 X
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
    업로드된 이미지를 받아 YOLO로 객체 감지 후,
    지정 클래스만 필터링하여 JSON으로 반환.
    감지된 각 객체에 대해 ms 단위 호출 시각도 함께 포함.
    """
    image = request.files.get('image')                 # multipart/form-data로 온 'image' 파일
    if not image:
        return jsonify({"error": "No image received"}), 400

    # 간단 구현: 디스크에 저장 후 경로로 추론
    # (동시 요청 경합 방지 위해 실제 서비스에서는 UUID 파일명/메모리 추론 권장)
    image_path = 'temp_image.jpg'
    image.save(image_path)

    # YOLO 추론 실행(단일 이미지면 results 길이는 보통 1)
    results = model(image_path)
    # boxes.data: [x1, y1, x2, y2, conf, class_id] (Tensor → numpy)
    detections = results[0].boxes.data.cpu().numpy()

    # 타깃 클래스 매핑
    #   COCO 기준: 0=person, 2=car, 7=truck, 15는 bench임(rock 아님)
    #   실제 rock 감지가 필요하면 커스텀 학습 모델 사용 필요
    target_classes = {0: "person", 2: "car", 7: "truck", 15: "rock"}
    filtered_results = []

    # ✔ 감지 시각(밀리초 포함) 문자열 생성 함수
    def now_ms():
        now = datetime.now()
        return now.strftime("%Y-%m-%d %H:%M:%S.") + f"{int(now.microsecond / 1000):03d}"

    # 감지된 객체 순회 → 타깃 클래스만 선별하고 로그/응답에 시각 포함
    for box in detections:
        class_id = int(box[5])
        if class_id in target_classes:
            detect_time = now_ms()  # 이 객체가 처리된 시각(서버 기준)
            print(f"🎯 인식된 물체: {target_classes[class_id]}  |  호출 시간: {detect_time}")

            filtered_results.append({
                'className': target_classes[class_id],          # 클래스 이름
                'bbox': [float(coord) for coord in box[:4]],    # 바운딩 박스 [x1,y1,x2,y2]
                'confidence': float(box[4]),                    # 신뢰도(0~1)
                'color': '#00FF00',                             # 프론트 시각화용 색상(예시)
                'filled': False,                                # 프론트 옵션(예시)
                'updateBoxWhileMoving': False,                  # 프론트 옵션(예시)
                'detect_time': detect_time                      # 감지 시각(문자열)
            })

    return jsonify(filtered_results)

@app.route('/info', methods=['POST'])
def info():
    """
    시뮬레이터 측 상태 정보 수신(예: 시간, 점수 등).
    현재는 단순히 수신 성공 응답만 반환.
    """
    data = request.get_json(force=True)                # Content-Type 상관없이 JSON 파싱 시도
    if not data:
        return jsonify({"error": "No JSON received"}), 400

    # 예시: 일정 시간이 지나면 자동 제어 신호를 응답하도록 할 수도 있음(주석 참조)
    # if data.get("time", 0) > 15:
    #     return jsonify({"status": "success", "control": "pause"})

    return jsonify({"status": "success", "control": ""})

@app.route('/get_action', methods=['POST'])
def get_action():
    """
    시뮬레이터가 보낸 현재 위치/포탑 상태를 참고하여
    다음 행동 명령을 반환.
    - 현재 코드는 준비된 combined_commands에서 하나를 꺼내 응답.
    - 실제 의사결정 로직(탐지 결과 반영/경로 계획 등)은 필요에 따라 추가.
    """
    data = request.get_json(force=True)

    # 상태 파싱(현재는 로깅만)
    position = data.get("position", {})
    turret = data.get("turret", {})
    pos_x = position.get("x", 0)
    pos_y = position.get("y", 0)
    pos_z = position.get("z", 0)
    turret_x = turret.get("x", 0)
    turret_y = turret.get("y", 0)

    print(f"📨 Position received: x={pos_x}, y={pos_y}, z={pos_z}")
    print(f"🎯 Turret received: x={turret_x}, y={turret_y}")

    # 큐에 남은 액션이 있으면 pop(0)으로 하나 꺼내고, 없으면 STOP 반환
    if combined_commands:
        command = combined_commands.pop(0)
    else:
        command = {
            "moveWS": {"command": "STOP", "weight": 1.0},
            "moveAD": {"command": "", "weight": 0.0},
            "turretQE": {"command": "", "weight": 0.0},
            "turretRF": {"command": "", "weight": 0.0},
            "fire": False
        }

    print("🔁 Sent Combined Action:", command)
    return jsonify(command)

@app.route('/update_bullet', methods=['POST'])
def update_bullet():
    """
    포탄 명중/충돌 보고 수신 — 현재는 로그만 남기고 OK 반환.
    (발사 간격 측정이 목적이라면 여기서 타임스탬프를 기록/차분하여 통계 가능)
    """
    data = request.get_json()
    if not data:
        return jsonify({"status": "ERROR", "message": "Invalid request data"}), 400

    print(f"💥 Bullet Impact at X={data.get('x')}, Y={data.get('y')}, Z={data.get('z')}, Target={data.get('hit')}")
    return jsonify({"status": "OK", "message": "Bullet impact data received"})

@app.route('/set_destination', methods=['POST'])
def set_destination():
    """
    이동 목표 좌표를 "x,y,z" 문자열로 받아 float으로 파싱 → 확인 응답.
    형식 오류 시 400 반환.
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
    장애물 정보 수신 — 현재는 콘솔에 출력만.
    """
    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': 'No data received'}), 400

    print("🪨 Obstacle Data:", data)
    return jsonify({'status': 'success', 'message': 'Obstacle data received'})

@app.route('/collision', methods=['POST']) 
def collision():
    """
    충돌 이벤트 수신(오브젝트명 + 좌표) — 콘솔에 로그 남기고 OK 반환.
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

# 에피소드 시작 시 호출되는 초기 설정 엔드포인트
@app.route('/init', methods=['GET'])
def init():
    """
    시뮬레이터 초기 설정값 반환.
    """
    config = {
        "startMode": "start",  # 시작 시 상태: "start" or "pause"
        "blStartX": 60,  "blStartY": 10, "blStartZ": 27.23,  # Blue 시작 좌표
        "rdStartX": 59,  "rdStartY": 10, "rdStartZ": 280,    # Red 시작 좌표
        "trackingMode": True,   # 추적 모드 ON/OFF
        "detectMode": True,     # 오탈자 의심: detectMode 권장
        "logMode": False,
        "enemyTracking": False,
        "saveSnapshot": False,
        "saveLog": False,
        "saveLidarData": False,
        "lux": 30000            # 조도 값(예시)
    }
    print("🛠️ Initialization config sent via /init:", config)
    return jsonify(config)

@app.route('/start', methods=['GET'])
def start():
    """
    시뮬레이션 시작 신호 — 간단 확인 응답.
    """
    print("🚀 /start command received")
    return jsonify({"control": ""})

if __name__ == '__main__':
    # 개발용 내장 서버 실행(0.0.0.0: 외부 접속 허용, 포트 5000)
    # 운영환경에서는 Gunicorn/Uvicorn 같은 WSGI/ASGI 서버 사용 권장
    app.run(host='0.0.0.0', port=5000)
