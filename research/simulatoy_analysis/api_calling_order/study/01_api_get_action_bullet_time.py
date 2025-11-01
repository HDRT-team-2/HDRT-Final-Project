"""
목적 : 이 코드는 api에서 탱크가 포탄을 발사하였을때 
       포탄과 포탄사이의 시간 간격을 알아보기 위해서 측정 된 코드
"""
from flask import Flask, request, jsonify
import os
import torch
from ultralytics import YOLO

app = Flask(__name__)

# YOLOv8 nano 가중치 로드 (COCO 80클래스)
model = YOLO('yolov8n.pt')

# 시뮬레이터에 보낼 예시 명령 시퀀스(큐처럼 사용: pop(0)로 맨 앞을 꺼냄)
combined_commands = [
    {
        "moveWS": {"command": "W", "weight": 1.0},  # 전진 강하게
        "moveAD": {"command": "D", "weight": 1.0},  # 우측으로 강하게
        "turretQE": {"command": "Q", "weight": 0.7},# 포탑 좌회전
        "turretRF": {"command": "R", "weight": 0.5},# 포각 상승
        "fire": False
    },
    # ... 이하 유사 구조 생략 (각 스텝마다 다른 움직임/사격 플래그)
    # 마지막 항목까지 동일 구조로 준비되어 있음
]

@app.route('/detect', methods=['POST'])
def detect():
    # 프론트/시뮬레이터에서 업로드한 이미지 파일 받기
    image = request.files.get('image')
    if not image:
        return jsonify({"error": "No image received"}), 400

    # 임시로 디스크에 저장(간단 구현). 실제 운영에선 메모리 처리/고유 파일명 권장
    image_path = 'temp_image.jpg'
    image.save(image_path)

    # YOLO 추론 수행
    results = model(image_path)
    # boxes.data: [x1, y1, x2, y2, conf, class_id] 형태의 텐서
    detections = results[0].boxes.data.cpu().numpy()

    # 타겟 클래스 필터링(예시)
    #    rock이 필요한 경우 커스텀 학습 또는 라벨 매핑 수정 필요.
    target_classes = {0: "person", 2: "car", 7: "truck", 15: "rock"}

    filtered_results = []
    for box in detections:
        class_id = int(box[5])
        if class_id in target_classes:
            filtered_results.append({
                'className': target_classes[class_id],    # 표시할 클래스명
                'bbox': [float(coord) for coord in box[:4]], # [x1,y1,x2,y2]
                'confidence': float(box[4]),              # 신뢰도
                'color': '#00FF00',                       # 프론트용 박스 색상
                'filled': False,
                'updateBoxWhileMoving': False
            })

    return jsonify(filtered_results)

@app.route('/info', methods=['POST'])
def info():
    # 시뮬레이터 상태 정보 수신용(예: 시간, 점수, 시스템 상태 등)
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "No JSON received"}), 400

    # 예: 시간 경과에 따른 자동 제어(주석 처리된 샘플 로직)
    # if data.get("time", 0) > 15:
    #     return jsonify({"status": "success", "control": "pause"})
    # if data.get("time", 0) > 15:
    #     return jsonify({"status": "success", "control": "reset"})

    # 현재는 별도 제어 없이 OK만 응답
    return jsonify({"status": "success", "control": ""})

@app.route('/get_action', methods=['POST'])
def get_action():
    # 시뮬레이터가 현재 위치/포탑 각도 등 상태를 전송하면,
    # 서버는 그에 맞는 다음 행동을 계산해 반환하는 엔드포인트
    data = request.get_json(force=True)

    position = data.get("position", {})
    turret = data.get("turret", {})

    pos_x = position.get("x", 0)
    pos_y = position.get("y", 0)
    pos_z = position.get("z", 0)

    turret_x = turret.get("x", 0)
    turret_y = turret.get("y", 0)

    # 준비된 시퀀스가 있으면 하나 꺼내서 쓰고,
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

    #    항상 fire=True인 동일 명령을 반환하게 됨(의도 확인 필요).
    command = {
        "moveWS": {"command": "", "weight": 0.0},
        "moveAD": {"command": "", "weight": 0.0},
        "turretQE": {"command": "", "weight": 0.0},
        "turretRF": {"command": "", "weight": 0.0},
        "fire": True
    }
    return jsonify(command)

@app.route('/update_bullet', methods=['POST'])
def update_bullet():
    # 포탄 명중(충돌) 결과를 시뮬레이터가 보고하는 엔드포인트
    data = request.get_json()
    if not data:
        return jsonify({"status": "ERROR", "message": "Invalid request data"}), 400

    print(f"💥 Bullet Impact at X={data.get('x')}, Y={data.get('y')}, Z={data.get('z')}, Target={data.get('hit')}")
    return jsonify({"status": "OK", "message": "Bullet impact data received"})

@app.route('/set_destination', methods=['POST'])
def set_destination():
    # 이동 목표 좌표 설정("x,y,z" 문자열로 전달받음)
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
    # 장애물 정보 업데이트(좌표/크기/종류 등) 수신용
    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': 'No data received'}), 400

    return jsonify({'status': 'success', 'message': 'Obstacle data received'})

@app.route('/collision', methods=['POST']) 
def collision():
    # 충돌 이벤트(오브젝트명 + 위치) 수신
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

# 에피소드 시작시 호출되는 초기 설정 엔드포인트
@app.route('/init', methods=['GET'])
def init():
    # 시뮬레이터 초기 설정 값 전달
    config = {
        "startMode": "start",  # "start" or "pause": 시작 시 상태
        "blStartX": 60,  # Blue 팀 시작 좌표
        "blStartY": 10,
        "blStartZ": 27.23,
        "rdStartX": 59,  # Red 팀 시작 좌표
        "rdStartY": 10,
        "rdStartZ": 280,
        "trackingMode": True,   # 추적 모드 on/off
        "detectMode": True,  
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
    # 에피소드/시뮬레이션 시작 트리거(필요시 제어 필드 추가 가능)
    print("🚀 /start command received")
    return jsonify({"control": ""})

if __name__ == '__main__':
    # 외부 접속 허용(0.0.0.0), 기본 포트 5000
    app.run(host='0.0.0.0', port=5000)
