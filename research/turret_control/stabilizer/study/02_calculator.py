# 적 전차와 아군 전차의 위치 간의 관계 파악 후 yaw, pitch 각도 계산해서 print되는 코드

# Flask 웹 서버, torch, YOLO, CSV, datetime, 수학 라이브러리 임포트
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
# 아군과 적군 위치로 yaw/pitch 절대/상대각도 계산
# -------------------------
def stabilizer(ally_pos, turret_angles, enemy_pos):
    dx = enemy_pos['x'] - ally_pos['x']  # X 거리
    dy = enemy_pos['y'] - ally_pos['y']  # Y 거리
    dz = enemy_pos['z'] - ally_pos['z']  # Z 거리

    # yaw 계산 (절대값)
    yaw_rad = math.atan2(-dx, dz)
    target_yaw = math.degrees(yaw_rad)
    if target_yaw < 0:
        target_yaw += 360

    # XZ 평면 거리 계산
    distance_xz = math.hypot(dx, dz)

    # pitch 계산 (절대값), 최대 ±90도 제한
    target_pitch = math.degrees(math.atan2(dy, distance_xz))
    target_pitch = max(min(target_pitch, 90), -90)

    # turret 기준 상대 yaw/pitch 계산
    yaw_relative = target_yaw - turret_angles['yaw']
    yaw_relative = (yaw_relative + 180) % 360 - 180  # -180~180 범위로 변환
    pitch_relative = target_pitch - turret_angles['pitch']

    return {
        'yaw_absolute': target_yaw,
        'pitch_absolute': target_pitch,
        'yaw_relative': yaw_relative,
        'pitch_relative': pitch_relative
    }

# -------------------------
# /info 엔드포인트
# 클라이언트에서 전차 상태 정보 수신
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

    # 시간, 거리 정보 저장
    time = data["time"]
    distance = data["distance"]

    # 플레이어 전차 정보 저장
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

    print(f"turret_y from simulator: {player_turret_x},{player_turret_y}")

    # 적 전차 정보 저장
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
# turret yaw/pitch 계산 후 명령 반환
# -------------------------
@app.route('/get_action', methods=['POST'])
def get_action():
    data = request.get_json(force=True)

    # 플레이어/적 전차 위치 유연하게 처리 (키 대소문자 대응)
    ally_pos = data.get('player_pos') or data.get('playerPos') or {'x':0,'y':0,'z':0}
    enemy_pos = data.get('enemy_pos') or data.get('enemyPos') or {'x':0,'y':0,'z':10}

    # 터렛 각도
    turret_angles = {
        'yaw': data.get('turretYaw', data.get('tankYaw', 0.0)),
        'pitch': data.get('turretPitch', 0.0)
    }

    # stabilizer 호출
    stab = stabilizer(ally_pos, turret_angles, enemy_pos)

    # 터렛 회전 임계값 설정
    yaw_threshold = 1.0
    pitch_threshold = 1.0
    turret_command = ""
    pitch_command = ""

    # 상대 yaw/pitch 기준 명령 결정
    if abs(stab['yaw_relative']) > yaw_threshold:
        turret_command = "Q" if stab['yaw_relative'] > 0 else "E"
    if abs(stab['pitch_relative']) > pitch_threshold:
        pitch_command = "R" if stab['pitch_relative'] > 0 else "F"

    # 목표 각도 근접 시 회전 정지
    if abs(stab['yaw_relative']) <= yaw_threshold and abs(stab['pitch_relative']) <= pitch_threshold:
        turret_command = ""
        pitch_command = ""

    print(f"[DEBUG] yaw={stab['yaw_relative']:.2f}, pitch={stab['pitch_relative']:.2f} → {turret_command}, {pitch_command}")

    return jsonify({
        "stab": stab,
        "commands": {
            "yaw": turret_command,
            "pitch": pitch_command
        }
    })

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

@app.route('/start', methods=['GET'])
def start():
    print("/start command received")
    return jsonify({"control": ""})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)