"""
목적 : 이 코드는 get_action(이동(Q,W,D,R), 포탄 발사)과 
       detect(탐지), collision(장애물 충돌)의 함수가 발생했을때
       API의 순서를 나타내기 위한 코드
"""
from flask import Flask, request, jsonify
import os
import torch
from ultralytics import YOLO

# Flask 애플리케이션 인스턴스 생성
app = Flask(__name__)

# YOLOv8 nano 모델 로드 (COCO 80 클래스 사전학습 가중치)
# - 서버 시작 시 1회 로드하여 전역으로 재사용 → 추론 지연 감소
model = YOLO('yolov8n.pt')

# 시뮬레이터에 순차적으로 보낼 예시 액션 시퀀스(큐 역할)
# - /get_action 호출 때마다 맨 앞 요소를 pop(0)으로 꺼내 사용
combined_commands = [
    {
        "moveWS": {"command": "W", "weight": 1.0},  # 전/후: W(전진), 강도 1.0
        "moveAD": {"command": "D", "weight": 1.0},  # 좌/우: D(우측), 강도 1.0
        "turretQE": {"command": "Q", "weight": 0.7},# 포탑 좌우: Q(좌회전), 강도 0.7
        "turretRF": {"command": "R", "weight": 0.5},# 포각 상하: R(상향), 강도 0.5
        "fire": False                                # 사격 안 함
    },
]


@app.route('/detect', methods=['POST'])
def detect():
    """
    업로드된 이미지를 받아 YOLO로 객체 감지하고,
    타깃 클래스(아래 target_classes에 정의)만 골라서 JSON 목록으로 반환.
    """
    image = request.files.get('image')                 # multipart/form-data의 'image' 필드
    if not image:
        return jsonify({"error": "No image received"}), 400

    # 간단 구현: 파일로 저장 후 경로 기반 추론
    # - 동시 요청 경합 방지를 위해 실제 서비스에서는 UUID 파일명/메모리 추론 권장
    image_path = 'temp_image.jpg'
    image.save(image_path)

    # YOLO 추론 실행
    results = model(image_path)

    # 첫 번째 결과의 바운딩 박스 텐서를 numpy로 변환
    # 형식: [x1, y1, x2, y2, conf, class_id]
    detections = results[0].boxes.data.cpu().numpy()

    # 타깃 클래스 매핑
    #   COCO 기준: 0=person, 2=car, 7=truck. (15는 bench)
    #   현재 15→"rock"은 COCO와 불일치하므로 실제 rock 감지를 원하면 커스텀 모델 필요
    target_classes = {0: "person", 2: "car", 7: "truck", 15: "rock"}

    filtered_results = []
    for box in detections:
        class_id = int(box[5])
        if class_id in target_classes:
            filtered_results.append({
                'className': target_classes[class_id],           # 클래스 이름
                'bbox': [float(coord) for coord in box[:4]],     # [x1,y1,x2,y2]
                'confidence': float(box[4]),                     # 0~1 신뢰도
                'color': '#00FF00',                              # 프론트 표시 색(예시)
                'filled': False,                                  # 프론트 옵션(예시)
                'updateBoxWhileMoving': False                    # 프론트 옵션(예시)
            })

    return jsonify(filtered_results)

@app.route('/info', methods=['POST'])
def info():
    """
    시뮬레이터의 상태 정보를 수신(예: 시간, 점수 등).
    현재는 단순히 유효성만 검사하고 성공 응답을 반환.
    """
    data = request.get_json(force=True)                # Content-Type이 달라도 강제 파싱
    if not data:
        return jsonify({"error": "No JSON received"}), 400

    # 예시 로직(주석): 특정 시간이 지나면 자동 pause/reset 제어를 내려줄 수 있음
    # if data.get("time", 0) > 15:
    #     return jsonify({"status": "success", "control": "pause"})
    # if data.get("time", 0) > 15:
    #     return jsonify({"status": "success", "control": "reset"})

    return jsonify({"status": "success", "control": ""})

@app.route('/get_action', methods=['POST'])
def get_action():
    """
    시뮬레이터가 보낸 현재 상태(position, turret)를 받아 다음 행동 명령을 반환.
    기본적으로 combined_commands에서 하나씩 꺼내 보내는 구조이나,
    현재 아래의 '고정 명령' 덮어쓰기 때문에 항상 STOP + fire=True를 반환하도록 되어 있음.
    (테스트 의도가 아니라면 덮어쓰기 블록을 제거/조건화해야 함)
    """
    data = request.get_json(force=True)

    # 상태 파싱(참고용 로그 출력; 현재 의사결정에는 사용하지 않음)
    position = data.get("position", {})
    turret = data.get("turret", {})
    pos_x = position.get("x", 0); pos_y = position.get("y", 0); pos_z = position.get("z", 0)
    turret_x = turret.get("x", 0); turret_y = turret.get("y", 0)

    print(f"📨 Position received: x={pos_x}, y={pos_y}, z={pos_z}")
    print(f"🎯 Turret received: x={turret_x}, y={turret_y}")

    # 준비된 명령이 남아 있으면 하나 꺼내 사용, 없으면 STOP 기본값
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

    #   현재 덮어쓰기: 위에서 만든 command를 무시하고 항상 STOP + fire=True 응답
    #   의도대로 시퀀스를 쓰려면 이 블록을 제거하거나 조건부로만 실행하세요.
    command = {
        "moveWS": {"command": "W", "weight": 1.0},
        "moveAD": {"command": "D", "weight": 1.0},
        "turretQE": {"command": "Q", "weight": 1.0},
        "turretRF": {"command": "R", "weight": 1.0},
        "fire": True
    }

    print("🔁 Sent Combined Action:", command)
    return jsonify(command)

@app.route('/update_bullet', methods=['POST'])
def update_bullet():
    """
    포탄 명중(충돌) 이벤트 리포트를 수신하여 로그에 출력.
    - 현재는 수신 확인만 수행하며, 간격/통계 계산은 미구현.
    - 발사 간격 측정이 목적이면 여기서 time.monotonic() 등을 기록·차분하는 로직을 추가.
    """
    data = request.get_json()
    if not data:
        return jsonify({"status": "ERROR", "message": "Invalid request data"}), 400

    print(f"💥 Bullet Impact at X={data.get('x')}, Y={data.get('y')}, Z={data.get('z')}, Target={data.get('hit')}")
    return jsonify({"status": "OK", "message": "Bullet impact data received"})

@app.route('/set_destination', methods=['POST'])
def set_destination():
    """
    이동 목표 좌표를 문자열 "x,y,z" 형태로 받아 float으로 파싱 후 확인 응답.
    - 잘못된 형식이면 400 반환.
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
    장애물(Obstacle) 정보 수신. 현재는 콘솔에 출력만 하고 성공 응답.
    """
    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': 'No data received'}), 400

    print("🪨 Obstacle Data:", data)
    return jsonify({'status': 'success', 'message': 'Obstacle data received'})

@app.route('/collision', methods=['POST']) 
def collision():
    """
    충돌(Collision) 이벤트 수신. 오브젝트 이름과 좌표를 로그에 출력하고 성공 응답.
    """
    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': 'No collision data received'}), 400

    object_name = data.get('objectName')
    position = data.get('position', {})
    x = position.get('x'); y = position.get('y'); z = position.get('z')

    print(f"💥 Collision Detected - Object: {object_name}, Position: ({x}, {y}, {z})")
    return jsonify({'status': 'success', 'message': 'Collision data received'})

# 에피소드 시작 시 호출되는 초기화 엔드포인트
@app.route('/init', methods=['GET'])
def init():
    """
    시뮬레이터 초기 설정 값 반환.
    """
    config = {
        "startMode": "start",  # "start" 또는 "pause"
        "blStartX": 60,  "blStartY": 10, "blStartZ": 27.23,  # Blue 시작 위치
        "rdStartX": 59,  "rdStartY": 10, "rdStartZ": 280,    # Red 시작 위치
        "trackingMode": True,   # 추적 모드
        "detectMode": True, 
        "logMode": True,        # 로그 모드
        "enemyTracking": False,  # 적 추적 모드
        "saveSnapshot": False,   # 스냅샷 저장
        "saveLog": False,        # 로그 저장
        "saveLidarData": False,  # 라이다 저장
        "lux": 30000             # 조도(예시)
    }
    print("🛠️ Initialization config sent via /init:", config)
    return jsonify(config)

@app.route('/start', methods=['GET'])
def start():
    """시뮬레이션 시작 신호(간단 확인 응답)"""
    print("🚀 /start command received")
    return jsonify({"control": ""})

if __name__ == '__main__':
    # 개발용 내장 서버 실행
    # - 0.0.0.0: 외부 접속 허용
    # - 운영 환경에서는 Gunicorn/Uvicorn 같은 WSGI/ASGI 서버 사용 권장
    app.run(host='0.0.0.0', port=5000)
