from flask import Flask, request, jsonify
import os
import torch
from ultralytics import YOLO
import csv
from datetime import datetime
import math

time = None
distance = None
arrived_flag = False  # 목표 도착 플래그 추가

# Player Tank
player_x = 0 # pos x
player_y = 0 # altitude
player_z = 0 # pos y

player_speed = 0
player_health = 0
player_turret_x = 0 # theta x
player_turret_y = 0 # theta y
player_body_x = 0 # theta x
player_body_y = 0 # theta y
player_body_z = 0

# Enemy Tank
enemy_x = 0 # pos x
enemy_y = 0 # altitude
enemy_z = 0 # pos y 

enemy_speed = 0
enemy_health = 0
enemy_turret_x = 0 # theta x
enemy_turret_y = 0 # theta y
enemy_body_x = 0 # theta x
enemy_body_y = 0 # theta y
enemy_body_z = 0

stopped_in_decel = False
creep_started = False
first_call_get_action = True  # get_action 최초 실행 판별용 플래그

app = Flask(__name__)
model = YOLO('yolov8n.pt')

combined_commands = [
    {
        "moveWS": {"command": "W", "weight": 0.0},
        "moveAD": {"command": "D", "weight": 0.0},
        "turretQE": {"command": "Q", "weight": 0.0},
        "turretRF": {"command": "R", "weight": 0.0},
        "fire": False
    }
]

# 상태 플래그 (파일 상단 전역 선언 위치에 추가)
stopped_in_decel = False
creep_started = False

@app.route('/info', methods=['POST'])
def info():
    global time, distance
    global player_x, player_y, player_z
    global player_speed, player_health, player_turret_x, player_turret_y
    global player_body_x, player_body_y, player_body_z
    global enemy_x, enemy_y, enemy_z
    global enemy_speed, enemy_health, enemy_turret_x, enemy_turret_y
    global enemy_body_x, enemy_body_y, enemy_body_z

    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "No JSON received"}), 400

    time = data["time"]
    distance = data["distance"]

    player_x = data["playerPos"]["x"]
    player_y = data["playerPos"]["y"]
    player_z = data["playerPos"]["z"]

    player_speed = data["playerSpeed"]
    player_health = data["playerHealth"]
    player_turret_x = data["playerTurretX"]
    player_turret_y = data["playerTurretY"]
    player_body_x = data["playerBodyX"]
    player_body_y = data["playerBodyY"]
    player_body_z = data["playerBodyZ"]

    enemy_x = data["enemyPos"]["x"]
    enemy_y = data["enemyPos"]["y"]
    enemy_z = data["enemyPos"]["z"]

    enemy_speed = data["enemySpeed"]
    enemy_health = data["enemyHealth"]
    enemy_turret_x = data["enemyTurretX"]
    enemy_turret_y = data["enemyTurretY"]
    enemy_body_x = data["enemyBodyX"]
    enemy_body_y = data["enemyBodyY"]
    enemy_body_z = data["enemyBodyZ"]

    return jsonify({"status": "success", "control": ""})

def drive_to_pos(player_x, player_z, player_body_x, player_speed,
                         target_x, target_z,
                         stopped_in_decel, creep_started, arrived_flag):
    """
    기존 get_action 내부의 '회전 우선 / 속도·구간 로직' 부분을 분리한 함수.
    입력으로 상태값을 받고 (사이드 이펙트 없이) 반환값으로 action 및 갱신된 플래그들을 돌려줌.
    """
    # 도착 시 정지
    if arrived_flag:
        action = {
            "moveWS": {"command": "STOP", "weight": 1.0},
            "moveAD": {"command": "", "weight": 0.0},
            "turretQE": {"command": "", "weight": 0.0},
            "turretRF": {"command": "", "weight": 0.0},
            "fire": False
        }
        return action, stopped_in_decel, creep_started, arrived_flag

    # 목표 각도 및 차이
    dx = target_x - player_x
    dz = target_z - player_z
    print("Target Position:", target_x, target_z)
    target_angle = math.atan2(dx, dz)
    target_angle_deg = math.degrees(target_angle)

    angle_diff = (target_angle_deg - player_body_x + 360) % 360
    if angle_diff > 180:
        angle_diff -= 360

    # 거리 계산
    distance_to_target = math.sqrt(dx**2 + dz**2)

    # 회전 우선
    if abs(angle_diff) > 2.0:
        weight = 1.0 if abs(angle_diff) >= 10.0 else 0.1
        action = {
            "moveWS": {"command": "S", "weight": 0.0},
            "moveAD": {"command": "D" if angle_diff > 0 else "A", "weight": weight},
            "turretQE": {"command": "", "weight": 0.0},
            "turretRF": {"command": "", "weight": 0.0},
            "fire": False
        }
        return action, stopped_in_decel, creep_started, arrived_flag

    # 속도/구간 로직 파라미터
    decel_distance = 20.0
    arrive_threshold = 3.0
    stop_speed_threshold = 10.0

    # 최고속 구간
    if distance_to_target > decel_distance:
        print("Max Speed Zone")
        stopped_in_decel = False
        creep_started = False
        action = {
            "moveWS": {"command": "W", "weight": 1.0},
            "moveAD": {"command": "", "weight": 0.0},
            "turretQE": {"command": "", "weight": 0.0},
            "turretRF": {"command": "", "weight": 0.0},
            "fire": False
        }
        return action, stopped_in_decel, creep_started, arrived_flag

    # 감속 구간: 처음 진입 -> STOP
    if not stopped_in_decel:
        print("Deceleration Zone")
        action = {
            "moveWS": {"command": "STOP", "weight": 1.0},
            "moveAD": {"command": "", "weight": 0.0},
            "turretQE": {"command": "", "weight": 0.0},
            "turretRF": {"command": "", "weight": 0.0},
            "fire": False
        }
        try:
            v = float(player_speed)
        except Exception:
            v = 0.0
        if v <= stop_speed_threshold:
            stopped_in_decel = True
            print("stopped_in_decel_2:", stopped_in_decel)
        return action, stopped_in_decel, creep_started, arrived_flag

    # STOP 후 크리프 시작
    if stopped_in_decel and not creep_started:
        print("Creep zone")
        action = {
            "moveWS": {"command": "W", "weight": 0.7},
            "moveAD": {"command": "", "weight": 0.0},
            "turretQE": {"command": "", "weight": 0.0},
            "turretRF": {"command": "", "weight": 0.0},
            "fire": False
        }
        creep_started = True
        return action, stopped_in_decel, creep_started, arrived_flag

    # 이미 크리프 중이면 arrive_threshold 까지 천천히 이동, 도착 시 STOP 및 arrived_flag 셋
    if creep_started:
        print("Creep zone")
        print("Distance to Target:", distance_to_target)
        print("arrive_threshold:", arrive_threshold)
        if distance_to_target > arrive_threshold:
            print("Continue Creeping")
            action = {
                "moveWS": {"command": "W", "weight": 0.4},
                "moveAD": {"command": "", "weight": 0.0},
                "turretQE": {"command": "", "weight": 0.0},
                "turretRF": {"command": "", "weight": 0.0},
                "fire": False
            }
            return action, stopped_in_decel, creep_started, arrived_flag
        else:
            print("Creep Ended - Arrived")
            action = {
                "moveWS": {"command": "STOP", "weight": 1.0},
                "moveAD": {"command": "", "weight": 0.0},
                "turretQE": {"command": "", "weight": 0.0},
                "turretRF": {"command": "", "weight": 0.0},
                "fire": False
            }
            arrived_flag = True
            stopped_in_decel = False
            creep_started = False
            return action, stopped_in_decel, creep_started, arrived_flag

    # 기본 정지
    action = {
        "moveWS": {"command": "STOP", "weight": 1.0},
        "moveAD": {"command": "", "weight": 0.0},
        "turretQE": {"command": "", "weight": 0.0},
        "turretRF": {"command": "", "weight": 0.0},
        "fire": False
    }
    return action, stopped_in_decel, creep_started, arrived_flag

@app.route('/get_action', methods=['POST'])
def get_action():
    global player_x, player_z, player_body_x, player_speed
    global stopped_in_decel, creep_started, arrived_flag, first_call_get_action

    target_x = 182
    target_z = 84

    # 최초 호출 시 상태 초기화 (필요시)
    if 'first_call_get_action' in globals() and first_call_get_action:
        print("First call to /get_action - initializing state flags")
        stopped_in_decel = False
        creep_started = False
        first_call_get_action = False

    # (기존) /info에서 이미 전역 변수들이 갱신되므로 여기서는 직접 참조
    action, stopped_in_decel, creep_started, arrived_flag = drive_to_pos(
        player_x, player_z, player_body_x, player_speed,
        target_x, target_z,
        stopped_in_decel, creep_started, arrived_flag
    )

    print("stopped_in_decel:", stopped_in_decel)

    return jsonify(action)

#Endpoint called when the episode starts
@app.route('/init', methods=['GET'])
def init():
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
        "logMode": False,
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
