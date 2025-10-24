from flask import Flask, request, jsonify
import os
import torch
from ultralytics import YOLO
import time

app = Flask(__name__)
model = YOLO('yolov8n.pt')

# --------------------------------------------
# start_time 글로벌 선언
start_time = None
# --------------------------------------------

combined_commands = [
    {
        "moveWS": {"command": "W", "weight": 1.0},
        "moveAD": {"command": "D", "weight": 1.0},
        "turretQE": {"command": "Q", "weight": 0.7},
        "turretRF": {"command": "R", "weight": 0.5},
        "fire": False
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
    image = request.files.get('image')
    if not image:
        return jsonify({"error": "No image received"}), 400

    image_path = 'temp_image.jpg'
    image.save(image_path)

    results = model(image_path)
    detections = results[0].boxes.data.cpu().numpy()

    target_classes = {0: "person", 2: "car", 7: "truck", 15: "rock"}
    filtered_results = []
    for box in detections:
        class_id = int(box[5])
        if class_id in target_classes:
            filtered_results.append({
                'className': target_classes[class_id],
                'bbox': [float(coord) for coord in box[:4]],
                'confidence': float(box[4]),
                'color': '#00FF00',
                'filled': False,
                'updateBoxWhileMoving': False
            })

    return jsonify(filtered_results)

@app.route('/info', methods=['POST'])
def info():
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "No JSON received"}), 400

    #print("📨 /info data received:", data)

    # Auto-pause after 15 seconds
    # if data.get("time", 0) > 15:
    #    return jsonify({"status": "success", "control": "pause"})
    # Auto-reset after 15 seconds
    #if data.get("time", 0) > 15:
    #    return jsonify({"stsaatus": "success", "control": "reset"})
    return jsonify({"status": "success", "control": ""})

@app.route('/get_action', methods=['POST'])
def get_action():
    # 글로벌 변수 추가, 스타트 타임
    # --------------------------------------------
    global start_time
    # --------------------------------------------

    # print("📨 Received JSON:", data)

    data = request.get_json(force=True)

    position = data.get("position", {})
    turret = data.get("turret", {})

    pos_x = position.get("x", 0)
    pos_y = position.get("y", 0)
    pos_z = position.get("z", 0)

    turret_x = turret.get("x", 0)
    turret_y = turret.get("y", 0)

    # 내가 추가한 구문
    # --------------------------------------------
    current_time = time.time()
    elapsed_time = 0

    if start_time is not None:
        elapsed_time = time.time() - start_time
    # --------------------------------------------

    print(f"📨 Position received: x={pos_x}, y={pos_y}, z={pos_z}")
    print(f"🎯 Turret received: x={turret_x}, y={turret_y}")

# 이건 내가 주석처리한거
    # if combined_commands:
    #     command = combined_commands.pop(0)
    # else:

# OLHS 20점 샘플링 결과 (w_weight, d_weight) - 분모 65 기준:
#  1: w = 46/65, d = 43/65
#  2: w = 63/65, d = 59/65
#  3: w = 42/65, d = 34/65
#  4: w = 51/65, d = 49/65
#  5: w = 59/65, d = 62/65
#  6: w = 3/5, d = 14/65
#  7: w = 23/65, d = 29/65
#  8: w = 43/65, d = 6/65
#  9: w = 1/65, d = 9/65
# 10: w = 4/65, d = 2/65
# 11: w = 27/65, d = 5/13
# 12: w = 23/65, d = 48/65
# 13: w = 7/13, d = 31/65
# 14: w = 31/65, d = 17/65
# 15: w = 58/65, d = 58/65
# 16: w = 19/65, d = 38/65
# 17: w = 1/5, d = 53/65
# 18: w = 16/65, d = 11/65
# 19: w = 2/13, d = 42/65
# 20: w = 54/65, d = 21/65

    command = {
        "moveWS": {"command": "W", "weight": 10 / 65},  # weight를 (원하는 최대 속도) / 65 로 주면 최대속도 도달 weight를 조절할 수 있다
        "moveAD": {"command": "D", "weight": 0.0},
        "turretQE": {"command": "", "weight": 0.0},
        "turretRF": {"command": "", "weight": 0.0},
        "fire": False
    }

    # 내가 추가한 구문
    # --------------------------------------------------------------------


    # 14초 시점에 우조향 추가
    if 14 <= elapsed_time:
        command = {
        "moveWS": {"command": "W", "weight": 10 / 65},
        "moveAD": {"command": "D", "weight": 42 / 65},
        "turretQE": {"command": "", "weight": 0.0},
        "turretRF": {"command": "", "weight": 0.0},
        "fire": False
    }
    # --------------------------------------------------------------------

    # Auto-pause after 15 seconds
    # if data.get("time", 1) > 15:
    #    return jsonify({"status": "success", "control": "pause"})

    # Auto-reset after 15 seconds
    # if data.get("time", 0) > 15:
    #    return jsonify({"stsaatus": "success", "control": "reset"})
    

    print("🔁 Sent Combined Action:", command)
    return jsonify(command)

@app.route('/update_bullet', methods=['POST'])
def update_bullet():
    data = request.get_json()
    if not data:
        return jsonify({"status": "ERROR", "message": "Invalid request data"}), 400

    print(f"💥 Bullet Impact at X={data.get('x')}, Y={data.get('y')}, Z={data.get('z')}, Target={data.get('hit')}")
    return jsonify({"status": "OK", "message": "Bullet impact data received"})

@app.route('/set_destination', methods=['POST'])
def set_destination():
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
    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': 'No data received'}), 400

    print("🪨 Obstacle Data:", data)
    return jsonify({'status': 'success', 'message': 'Obstacle data received'})

@app.route('/collision', methods=['POST']) 
def collision():
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

#Endpoint called when the episode starts
@app.route('/init', methods=['GET'])
def init():

    # 글로벌 함수 추가, 스타트 모드 시작 시점 기록
    global start_time
    start_time = time.time()

    config = {
        "startMode": "start",  # Options: "start" or "pause"
        "blStartX": 60,  #Blue Start Position
        "blStartY": 10,
        "blStartZ": 27.23,
        "rdStartX": 59, #Red Start Position
        "rdStartY": 10,
        "rdStartZ": 280,
        "trackingMode": True,
        "detactMode": False,
        "logMode": True,
        "enemyTracking": True,
        "saveSnapshot": False,
        "saveLog": True,
        "saveLidarData": False,
        "lux": 30000
    }
    print("🛠️ Initialization config sent via /init:", config)
    return jsonify(config)

@app.route('/start', methods=['GET'])
def start():
    print("🚀 /start command received")
    return jsonify({"control": ""})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
