"""
[디버깅 모드] 무조건 직진 + 스태빌라이저 테스트

1. 주행: 계산 로직 없이 무조건 'W'(전진) 명령만 내림.
2. 스태빌라이저: 전차가 직진하는 동안 포탑은 (250, 10, 250) 좌표를 계속 바라봄.
"""

import os
import math
from datetime import datetime
from flask import Flask, request, jsonify
import torch
from ultralytics import YOLO

app = Flask(__name__)

# YOLO (그대로 유지)
try:
    model = YOLO('yolov8n.pt')
except:
    pass

# ================= 유틸리티 =================
def normalize_angle_deg(angle: float) -> float:
    return (angle + 180.0) % 360.0 - 180.0

# ================= 스태빌라이저 클래스 =================
class SimpleTurretStabilizer:
    def __init__(self):
        self.Kp_fast = 0.4
        self.Kp_slow = 0.2
        self.Kff_ad  = 0.999
        self.SLOW_ZONE = 1.0  
        self.YAW_DEADBAND = 0.0 
        self.MAX_QE = 2.0
        self.MIN_QE_OUTPUT = 0.01

    def update(self, player_turret_x, target_x, player_x, target_z, player_z):
        # 1. 타깃 방향 계산
        dx = target_x - player_x
        dz = target_z - player_z
        target_yaw = math.degrees(math.atan2(dx, dz))
        if target_yaw < 0: target_yaw += 360.0

        # 2. 오차 계산
        yaw_err_now = normalize_angle_deg(target_yaw - player_turret_x)

        # 3. P 제어 (목표 바라보기)
        current_kp = self.Kp_fast if abs(yaw_err_now) > self.SLOW_ZONE else self.Kp_slow
        u = current_kp * yaw_err_now
        
        # 출력 제한
        if u > self.MAX_QE: u = self.MAX_QE
        elif u < -self.MAX_QE: u = -self.MAX_QE

        if abs(u) < self.MIN_QE_OUTPUT: return "", 0.0

        return ("E", u) if u > 0 else ("Q", -u)

yaw_stabilizer = SimpleTurretStabilizer()

# ================= 직사 조준 함수 =================
def calculate_direct_pitch(player_pos, target_pos, player_turret_y):
    dx = target_pos['x'] - player_pos['x']
    dy = target_pos['y'] - player_pos['y']
    dz = target_pos['z'] - player_pos['z']
    
    horizontal_dist = math.sqrt(dx**2 + dz**2)
    if horizontal_dist < 1.0: return "", 0.0

    target_pitch = math.degrees(math.atan2(dy, horizontal_dist))
    pitch_diff = target_pitch - player_turret_y
    
    if abs(pitch_diff) < 0.1: return "", 0.0
    weight = min(abs(pitch_diff) * 0.1, 1.0)
    
    return ("R", weight) if pitch_diff > 0 else ("F", weight)


# ================= 메인 로직 =================
@app.route('/get_action', methods=['POST'])
def get_action():
    data = request.get_json(force=True, silent=True) or {}

    # 1. 데이터 파싱
    ally_pos = data.get("ally_body_pos") or data.get("position") or {}
    turret_ang = data.get("ally_turret_angle") or data.get("turret") or {}
    
    # 목표가 없으면 강제로 (250, 10, 250) 설정
    target_pos = data.get("ibsm_target")
    if not target_pos:
        target_pos = {"x": 150.0, "y": 10.0, "z": 150.0}

    # 좌표 추출
    px = float(ally_pos.get("x", 0))
    py = float(ally_pos.get("y", 0))
    pz = float(ally_pos.get("z", 0))
    
    tx = float(target_pos.get("x", 0))
    ty = float(target_pos.get("y", 0))
    tz = float(target_pos.get("z", 0))
    
    p_turret_yaw = float(turret_ang.get("x", 0))
    p_turret_pitch = float(turret_ang.get("y", 0))

    # --- [수정됨] 무조건 직진 로직 ---
    # 복잡한 계산 다 버리고 그냥 'W'만 넣음
    b_steer = ""        # 조향 없음 (직진)
    b_throttle = "W"    # 전진
    
    # --- 스태빌라이저 (포탑만 목표 바라보기) ---
    qe_cmd, qe_w = yaw_stabilizer.update(p_turret_yaw, tx, px, tz, pz)
    rf_cmd, rf_w = calculate_direct_pitch(ally_pos, target_pos, p_turret_pitch)

    # --- 사격 판단 ---
    fire_cmd = False
    if qe_w < 0.3 and rf_w < 0.3:
        fire_cmd = False

    # --- 응답 생성 ---
    command = {
        "moveWS": {
            "command": b_throttle, 
            "weight": 0.6  # 무조건 풀악셀
        },
        "moveAD": {
            "command": b_steer, 
            "weight": 0.0
        },
        "turretQE": {
            "command": qe_cmd, 
            "weight": qe_w
        },
        "turretRF": {
            "command": rf_cmd, 
            "weight": rf_w
        },
        "fire": fire_cmd
    }

    # 디버깅 출력
    # print(f"🚀 직진 중! 포탑: {qe_cmd} (목표: {tx}, {tz})")

    return jsonify(command)

# ================= 기타 필수 엔드포인트 (유지) =================
@app.route('/detect', methods=['POST'])
def detect(): return jsonify([]) 

@app.route('/info', methods=['POST'])
def info(): return jsonify({"status": "success", "control": ""})

@app.route('/update_bullet', methods=['POST'])
def update_bullet(): return jsonify({"status": "OK"})

@app.route('/set_destination', methods=['POST'])
def set_destination(): return jsonify({"status": "OK"})

@app.route('/update_obstacle', methods=['POST'])
def update_obstacle(): return jsonify({'status': 'success'})

@app.route('/collision', methods=['POST']) 
def collision(): return jsonify({'status': 'success'})

@app.route('/init', methods=['GET'])
def init():
    config = {
        "startMode": "start",
        "blStartX": 50, "blStartY": 10, "blStartZ": 10,
        "rdStartX": 150, "rdStartY": 10, "rdStartZ": 150,
        "trackingMode": True, "detactMode": False, "logMode": False,
        "enemyTracking": False, "saveSnapshot": False, "saveLog": False,
        "saveLidarData": False, "lux": 30000, "destoryObstaclesOnHit" : True
    }
    return jsonify(config)

@app.route('/start', methods=['GET'])
def start(): return jsonify({"control": ""})

if __name__ == '__main__':
    print("=== 무조건 직진 서버 실행 (포트 4000) ===")
    app.run(host='0.0.0.0', port=4000)