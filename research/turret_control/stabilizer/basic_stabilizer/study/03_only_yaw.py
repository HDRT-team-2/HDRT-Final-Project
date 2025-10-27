# 적 전차와 아군 전차 위치에 따라 각도를 계산 후 적 전차의 위치에 포탑이 가게끔 만든 코드(포신 높낮이 조절은 X)

# -------------------------
# Flask 웹 서버, torch, YOLO, CSV, datetime, 수학 라이브러리 임포트
# -------------------------
from flask import Flask, request, jsonify
import os
import torch
from ultralytics import YOLO
import csv
from datetime import datetime
import math

# -------------------------
# 웨이포인트 관리 (연결 리스트 형태)
# -------------------------
class WaypointNode:
    def __init__(self, x, z, arrived=False):
        self.x = float(x)       # X 좌표
        self.z = float(z)       # Z 좌표
        self.arrived = bool(arrived) # 도착 여부
        self.next = None        # 다음 노드 포인터

class WaypointList:
    def __init__(self):
        self.head = None
        self.tail = None
        self._len = 0

    # 새 웨이포인트 추가
    def append(self, x, z, arrived=False):
        node = WaypointNode(x, z, arrived)
        if not self.head:
            self.head = self.tail = node
        else:
            self.tail.next = node
            self.tail = node
        self._len += 1
        return node

    # 첫 번째 웨이포인트 확인
    def peek(self):
        return self.head

    # 첫 번째 웨이포인트 제거
    def pop(self):
        if not self.head:
            return None
        node = self.head
        self.head = node.next
        if not self.head:
            self.tail = None
        node.next = None
        self._len -= 1
        return node

    # 첫 번째 웨이포인트 도착 표시
    def mark_head_arrived(self):
        if self.head:
            self.head.arrived = True
            return True
        return False

    # 웨이포인트 리스트가 비었는지 확인
    def is_empty(self):
        return self.head is None

    # 웨이포인트 리스트를 딕셔너리 리스트로 변환
    def to_list(self):
        out = []
        cur = self.head
        while cur:
            out.append({'x': cur.x, 'z': cur.z, 'arrived': cur.arrived})
            cur = cur.next
        return out

# -------------------------
# 전역 웨이포인트 리스트 초기화
# -------------------------
waypoints = WaypointList()
waypoints.append(182, 84)
waypoints.append(100, 187)
waypoints.append(25, 280)

# -------------------------
# 전역 변수 초기화 (시간, 거리, 플레이어/적 전차 상태)
# -------------------------
time = None
distance = None

# Player Tank 상태
player_x = 0
player_y = 0
player_z = 0

player_speed = 0
player_health = 0
player_turret_x = 0
player_turret_y = 0
player_body_x = 0
player_body_y = 0
player_body_z = 0

# Enemy Tank 상태
enemy_x = 0
enemy_y = 0
enemy_z = 0

enemy_speed = 0
enemy_health = 0
enemy_turret_x = 0
enemy_turret_y = 0
enemy_body_x = 0
enemy_body_y = 0
enemy_body_z = 0

# -------------------------
# Flask 앱 및 YOLO 모델 초기화
# -------------------------
app = Flask(__name__)
model = YOLO('yolov8n.pt')

# -------------------------
# stabilizer 함수
# 아군과 적군 위치로 yaw/pitch 절대값 계산
# 포신 높낮이는 고려하지 않음
# -------------------------
def stabilizer(ally_pos, enemy_pos):
    """
    ally_pos: {'x': , 'y': , 'z': } 아군 전차 위치
    enemy_pos: {'x': , 'y': , 'z': } 적 전차 위치

    반환: {'yaw', 'pitch'}
    """
    dx = enemy_pos['x'] - ally_pos['x']
    dz = enemy_pos['z'] - ally_pos['z']
    dy = enemy_pos['y'] - ally_pos['y']

    # XZ 평면 거리 계산
    distance_xz = math.hypot(dx, dz)

    # yaw 계산
    yaw_rad = math.atan2(dx, dz)
    target_yaw = math.degrees(yaw_rad)
    if target_yaw < 0:
        target_yaw += 360

    # pitch 계산 (포신 높이 조절 고려하지 않음)
    target_pitch = math.degrees(math.atan2(dy, distance_xz))

    return {
        'yaw': target_yaw,
        'pitch': target_pitch
    }

# -------------------------
# /info 엔드포인트
# 시뮬레이터로부터 전차 상태 정보 수신
# -------------------------
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

    # 시간과 거리 정보 업데이트
    time = data["time"]
    distance = data["distance"]

    # 플레이어 전차 상태 업데이트
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

    # 적 전차 상태 업데이트
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

# -------------------------
# /get_action 엔드포인트
# turret를 적 전차 위치를 바라보도록 계산 후 반환
# -------------------------
@app.route('/get_action', methods=['POST'])
def get_action():
    global player_x, player_y, player_z, player_turret_x, player_turret_y
    global enemy_x, enemy_y, enemy_z

    # 아군/적군 위치 정보 구성
    ally_pos = {'x': player_x, 'y': player_y, 'z': player_z}
    enemy_pos = {'x': enemy_x, 'y': enemy_y, 'z': enemy_z}

    # stabilizer 호출
    result = stabilizer(ally_pos, enemy_pos)
    print("result", result)

    # -------------------------
    # yaw 회전 명령 결정
    # -------------------------
    turret_qe_command = ""
    turret_qe_weight = 0.0
    yaw_angle_diff = result['yaw'] - player_turret_x
    if abs(yaw_angle_diff) > 1.0:
        turret_qe_command = "Q" if yaw_angle_diff < 0 else "E"
        turret_qe_weight = 1.0 if abs(yaw_angle_diff) >= 10.0 else 0.1

    # -------------------------
    # pitch 회전 명령 결정
    # -------------------------
    turret_rf_command = ""
    turret_rf_weight = 0.0
    pitch_angle_diff = result['yaw'] - player_turret_x  # 현재는 yaw 계산을 pitch에 그대로 사용 (필요시 수정)
    if abs(pitch_angle_diff) > 1.0:
        turret_rf_command = "R" if pitch_angle_diff < 0 else "F"
        turret_rf_weight = 1.0 if abs(pitch_angle_diff) >= 10.0 else 0.1

    # -------------------------
    # 주행 명령 없이 터렛 회전만 반환
    # -------------------------
    action = {
        "moveWS": {"command": "S", "weight": 0.0},  # 전진/후진 없음
        "moveAD": {"command": "", "weight": 0.0},   # 좌/우 회전 없음
        "turretQE": {"command": turret_qe_command, "weight": turret_qe_weight},
        "turretRF": {"command": turret_rf_command, "weight": turret_rf_weight},
        "fire": False
    }
    return jsonify(action)

# -------------------------
# /init 엔드포인트
# 시뮬레이션 초기 설정 반환
# -------------------------
@app.route('/init', methods=['GET'])
def init():
    config = {
        "startMode": "start",
        "blStartX": 60,
        "blStartY": 10,
        "blStartZ": 27.23,
        "rdStartX": 120,
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
    print("Initialization config sent via /init:", config)
    return jsonify(config)

# -------------------------
# /start 엔드포인트
# 시뮬레이션 시작 시 호출
# -------------------------
@app.route('/start', methods=['GET'])
def start():
    print("/start command received")
    return jsonify({"control": ""})

# -------------------------
# Flask 앱 실행
# -------------------------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
