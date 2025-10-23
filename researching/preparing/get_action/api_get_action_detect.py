"""
목적 : 이 코드는 get_action(이동, 포탄 발사)과 detect(탐지)의 함수가 발생했을때
       API의 순서를 나타내기 위한 코드
"""
from flask import Flask, request, jsonify
import os
import torch
from ultralytics import YOLO

app = Flask(__name__)

# YOLOv8 nano 가중치 로드 (COCO 80클래스 사전학습)
model = YOLO('yolov8n.pt')

# 시뮬레이터에 보낼 예시 명령 시퀀스(큐처럼 pop(0)으로 맨 앞부터 사용)
combined_commands = [
    {
        "moveWS": {"command": "W", "weight": 1.0},  # 전/후 움직임: 전진(W) 강하게
        "moveAD": {"command": "D", "weight": 1.0},  # 좌/우 움직임: 우측(D) 강하게
        "turretQE": {"command": "Q", "weight": 0.7},# 포탑 좌우 회전: Q(좌회전)
        "turretRF": {"command": "R", "weight": 0.5},# 포각 상하: R(상향)
        "fire": False                                # 발사 여부
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
    """업로드된 이미지를 받아 YOLO로 객체 감지 후 특정 클래스만 반환"""
    image = request.files.get('image')
    if not image:
        return jsonify({"error": "No image received"}), 400

    # 간단 구현: 파일로 저장 후 추론 (실서비스에선 메모리에서 바로 추론 권장)
    image_path = 'temp_image.jpg'
    image.save(image_path)

    # YOLO 추론 실행
    results = model(image_path)
    # boxes.data: [x1, y1, x2, y2, conf, class_id] 형태 (numpy로 변환)
    detections = results[0].boxes.data.cpu().numpy()

    # 타깃 클래스 매핑 (COCO 기준 0=person, 2=car, 7=truck)
    # ⚠ 주의: COCO에서 class_id 15는 bench임. rock은 COCO에 없음 → 커스텀 모델 필요.
    target_classes = {0: "person", 2: "car", 7: "truck", 15: "rock"}

    filtered_results = []
    for box in detections:
        class_id = int(box[5])
        if class_id in target_classes:
            filtered_results.append({
                'className': target_classes[class_id],        # 표시할 클래스명
                'bbox': [float(coord) for coord in box[:4]],  # 바운딩 박스 [x1,y1,x2,y2]
                'confidence': float(box[4]),                  # 신뢰도(0~1)
                'color': '#00FF00',                           # 프론트 표시용 색상
                'filled': False,
                'updateBoxWhileMoving': False
            })

    return jsonify(filtered_results)

@app.route('/info', methods=['POST'])
def info():
    """시뮬레이터 상태 정보 수신(시간/상태 등). 현재는 확인용으로 OK만 응답"""
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "No JSON received"}), 400

    # 예: 특정 시간 이후 자동 제어 로직(샘플)
    # if data.get("time", 0) > 15:
    #     return jsonify({"status": "success", "control": "pause"})
    # if data.get("time", 0) > 15:
    #     return jsonify({"status": "success", "control": "reset"})

    return jsonify({"status": "success", "control": ""})

@app.route('/get_action', methods=['POST'])
def get_action():
    """현재 위치/포탑 상태를 받고, 다음 행동 명령을 반환"""
    data = request.get_json(force=True)

    position = data.get("position", {})
    turret = data.get("turret", {})

    pos_x = position.get("x", 0)
    pos_y = position.get("y", 0)
    pos_z = position.get("z", 0)

    turret_x = turret.get("x", 0)
    turret_y = turret.get("y", 0)

    print(f"📨 Position received: x={pos_x}, y={pos_y}, z={pos_z}")
    print(f"🎯 Turret received: x={turret_x}, y={turret_y}")

    # 준비된 시퀀스가 있으면 하나 꺼내서 사용
    if combined_commands:
        command = combined_commands.pop(0)
    else:
        # 없으면 안전 정지 기본값
        command = {
            "moveWS": {"command": "STOP", "weight": 1.0},
            "moveAD": {"command": "", "weight": 0.0},
            "turretQE": {"command": "", "weight": 0.0},
            "turretRF": {"command": "", "weight": 0.0},
            "fire": False
        }

    #   현재 아래 블록이 위에서 만든 command를 덮어씀 → 항상 전진+발사(True)로 고정
    #   의도대로 시퀀스를 쓰려면 이 덮어쓰기 블록을 제거하거나 조건적으로 사용하세요.
    command = {
        "moveWS": {"command": "W", "weight": 1.0},
        "moveAD": {"command": "", "weight": 0.0},
        "turretQE": {"command": "", "weight": 0.0},
        "turretRF": {"command": "", "weight": 0.0},
        "fire": True
    }

    print("🔁 Sent Combined Action:", command)
    return jsonify(command)

@app.route('/update_bullet', methods=['POST'])
def update_bullet():
    """포탄 명중/충돌 보고 수신. 현재는 콘솔 로깅만 수행"""
    data = request.get_json()
    if not data:
        return jsonify({"status": "ERROR", "message": "Invalid request data"}), 400

    print(f"💥 Bullet Impact at X={data.get('x')}, Y={data.get('y')}, Z={data.get('z')}, Target={data.get('hit')}")
    return jsonify({"status": "OK", "message": "Bullet impact data received"})

@app.route('/set_destination', methods=['POST'])
def set_destination():
    """이동 목표 좌표("x,y,z")를 문자열로 받아 파싱 후 저장/응답"""
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
    """장애물 정보 수신(좌표/크기/종류 등). 현재는 수신 확인만"""
    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': 'No data received'}), 400

    print("🪨 Obstacle Data:", data)
    return jsonify({'status': 'success', 'message': 'Obstacle data received'})

@app.route('/collision', methods=['POST']) 
def collision():
    """충돌 이벤트 수신(오브젝트명 + 위치). 현재는 콘솔 로깅만"""
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
    config = {
        "startMode": "start",  # "start" 또는 "pause" (시작 상태)
        "blStartX": 60,  # Blue 시작 위치
        "blStartY": 10,
        "blStartZ": 27.23,
        "rdStartX": 59,  # Red 시작 위치
        "rdStartY": 10,
        "rdStartZ": 280,
        "trackingMode": True,   # 추적 모드 on/off
        "detectMode": True,     # 오탈자 가능성: 보통 detectMode 사용
        "logMode": True,
        "enemyTracking": False,
        "saveSnapshot": False,
        "saveLog": False,
        "saveLidarData": False,
        "lux": 30000            # 조도값(예시)
    }
    print("🛠️ Initialization config sent via /init:", config)
    return jsonify(config)

@app.route('/start', methods=['GET'])
def start():
    """시뮬레이션 시작 신호 응답"""
    print("🚀 /start command received")
    return jsonify({"control": ""})

if __name__ == '__main__':
    # 외부 접속 허용(0.0.0.0), 5000 포트로 서버 실행
    app.run(host='0.0.0.0', port=5000)
