# 적 전차와 아군 전차 위치에 따라 각도를 계산 후 적 전차의 위치에 포탑이 가게끔 만든 코드(포신 높낮이까지 완료(최종본))
# -----------------------------------------
# 적 전차와 아군 전차 위치 기반 포탑/포신 각도 계산 코드
# 포신 높낮이(pitch)까지 포함하여 최종 완성본
# -----------------------------------------

from flask import Flask, request, jsonify
import os
import torch
from ultralytics import YOLO
import csv
from datetime import datetime
import math

# -----------------------------------------
# 웨이포인트 연결 리스트 클래스 정의
# -----------------------------------------
class WaypointNode:
    """웨이포인트 노드: x, z 좌표와 도착 여부 저장"""
    def __init__(self, x, z, arrived=False):
        self.x = float(x)
        self.z = float(z)
        self.arrived = bool(arrived)
        self.next = None

class WaypointList:
    """웨이포인트 연결 리스트 관리 클래스"""
    def __init__(self):
        self.head = None
        self.tail = None
        self._len = 0

    def append(self, x, z, arrived=False):
        """리스트 끝에 새 웨이포인트 추가"""
        node = WaypointNode(x, z, arrived)
        if not self.head:
            self.head = self.tail = node
        else:
            self.tail.next = node
            self.tail = node
        self._len += 1
        return node

    def peek(self):
        """리스트의 첫 노드 반환"""
        return self.head

    def pop(self):
        """리스트의 첫 노드 제거 후 반환"""
        if not self.head:
            return None
        node = self.head
        self.head = node.next
        if not self.head:
            self.tail = None
        node.next = None
        self._len -= 1
        return node

    def mark_head_arrived(self):
        """첫 노드 도착 처리"""
        if self.head:
            self.head.arrived = True
            return True
        return False

    def is_empty(self):
        """리스트 비어 있는지 확인"""
        return self.head is None

    def to_list(self):
        """연결 리스트를 일반 리스트로 변환"""
        out = []
        cur = self.head
        while cur:
            out.append({'x': cur.x, 'z': cur.z, 'arrived': cur.arrived})
            cur = cur.next
        return out

# 전역 웨이포인트 리스트 초기화
waypoints = WaypointList()
waypoints.append(182, 84)
waypoints.append(100, 187)
waypoints.append(25, 280)

# -----------------------------------------
# 전역 변수 초기화
# -----------------------------------------
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

# Flask 앱 생성
app = Flask(__name__)
model = YOLO('yolov8n.pt')  # YOLO 모델 초기화

# -----------------------------------------
# 포탑 각도 계산 함수 (적 위치 기준)
# -----------------------------------------
def stabilizer(ally_pos, enemy_pos):
    """
    ally_pos: {'x', 'y', 'z'} 아군 전차 위치
    enemy_pos: {'x', 'y', 'z'} 적 전차 위치

    Returns:
        {'yaw', 'pitch'} : 목표 yaw, pitch 각도 (deg)
    """
    dx = enemy_pos['x'] - ally_pos['x']  # x축 거리
    dz = enemy_pos['z'] - ally_pos['z']  # z축 거리
    dy = enemy_pos['y'] - ally_pos['y']  # 높이 차이

    distance_xz = math.hypot(dx, dz)  # 평면 거리 계산

    # 목표 yaw 계산 (0° = 북쪽, 시계 방향 증가)
    yaw_rad = math.atan2(dx, dz)
    target_yaw = math.degrees(yaw_rad)
    if target_yaw < 0:
        target_yaw += 360

    # 목표 pitch 계산 (포신 높낮이)
    target_pitch = math.degrees(math.atan2(dy, distance_xz))

    return {
        'yaw': target_yaw,
        'pitch': target_pitch
    }

# -----------------------------------------
# /info : 시뮬레이터로부터 상태 정보 수신
# -----------------------------------------
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

    # 시간/거리
    time = data["time"]
    distance = data["distance"]

    # Player 정보
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

    # Enemy 정보
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

# -----------------------------------------
# /get_action : 포탑/포신 각도 조정 명령 반환
# -----------------------------------------
@app.route('/get_action', methods=['POST'])
def get_action():
    global player_x, player_y, player_z, player_turret_x, player_turret_y
    global enemy_x, enemy_y, enemy_z

    # 아군/적 위치 가져오기
    ally_pos = {'x': player_x, 'y': player_y, 'z': player_z}
    enemy_pos = {'x': enemy_x, 'y': enemy_y, 'z': enemy_z}

    # stabilizer 함수로 목표 yaw/pitch 계산
    result = stabilizer(ally_pos, enemy_pos)
    print("result", result)

    # -----------------------------------------
    # 포탑 수평(yaw) 회전 명령 계산
    # -----------------------------------------
    turret_qe_command = ""
    turret_qe_weight = 0.0
    yaw_angle_diff = result['yaw'] - player_turret_x
    if abs(yaw_angle_diff) > 1.0:
        turret_qe_command = "Q" if yaw_angle_diff < 0 else "E"
        turret_qe_weight = 1.0 if abs(yaw_angle_diff) >= 10.0 else 0.1

    # -----------------------------------------
    # 포신 수직(pitch) 회전 명령 계산
    # -----------------------------------------
    turret_rf_command = ""
    turret_rf_weight = 0.0
    pitch_angle_diff = result['pitch'] - player_turret_y
    if abs(pitch_angle_diff) > 1.0:
        turret_rf_command = "R" if pitch_angle_diff > 0 else "F"
        turret_rf_weight = 1.0 if abs(pitch_angle_diff) >= 10.0 else 0.1

    # -----------------------------------------
    # 이동 명령 없이 터렛/포신 회전 명령 반환
    # -----------------------------------------
    action = {
        "moveWS": {"command": "S", "weight": 0.0},  # 전진 없음
        "moveAD": {"command": "", "weight": 0.0},   # 좌우 회전 없음
        "turretQE": {"command": turret_qe_command, "weight": turret_qe_weight},
        "turretRF": {"command": turret_rf_command, "weight": turret_rf_weight},
        "fire": False
    }
    return jsonify(action)

# -----------------------------------------
# /init : 시뮬레이터 초기값 전달
# -----------------------------------------
@app.route('/init', methods=['GET'])
def init():
    config = {
        "startMode": "start",
        "blStartX": 30,
        "blStartY": 10,
        "blStartZ": 30,
        "rdStartX": 300,
        "rdStartY": 10,
        "rdStartZ": 30,
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

# -----------------------------------------
# /start : 시뮬레이터 시작 명령
# -----------------------------------------
@app.route('/start', methods=['GET'])
def start():
    print("/start command received")
    return jsonify({"control": ""})

# -----------------------------------------
# 메인 실행
#

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
