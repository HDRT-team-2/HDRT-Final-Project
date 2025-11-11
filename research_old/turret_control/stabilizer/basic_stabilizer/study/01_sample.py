# 적 전차를 중간에 두고 아군 전차의 포탑 각도 고정하여 적 전차를 보게 한 뒤, 원으로 돌 수 있도록 만든 코드

# Flask, torch, YOLO 라이브러리 임포트
from flask import Flask, request, jsonify
import os
import torch
from ultralytics import YOLO

# Flask 앱 초기화
app = Flask(__name__)

# YOLO 모델 로드 (yolov8n)
model = YOLO('yolov8n.pt')

# 포탑 회전 완료 후 원형 이동 여부 플래그
myFlag = False

# -------------------------
# /get_action 엔드포인트
# -------------------------
@app.route('/get_action', methods=['POST'])
def get_action():
    global myFlag

    # 클라이언트에서 JSON 데이터 수신
    data = request.get_json(force=True)

    # 위치와 터렛 데이터 추출
    position = data.get("position", {})
    turret = data.get("turret", {})

    pos_x = position.get("x", 0)
    pos_y = position.get("y", 0)
    pos_z = position.get("z", 0)

    turret_x = turret.get("x", 0)
    turret_y = turret.get("y", 0)

    # 수신된 값 출력 (디버그용)
    print(f"Position received: x={pos_x}, y={pos_y}, z={pos_z}")
    print(f"Turret received: x={turret_x}, y={turret_y}")

    # 반환할 명령 딕셔너리 초기화
    command = {}

    # -------------------------
    # 포탑이 아직 80도 미만일 때
    # 오른쪽으로 회전하면서 대기
    # -------------------------
    if not myFlag and turret_x < 80:
        command = {
            "turretQE": {"command": "E", "weight": 1.0},  # 포탑 오른쪽 회전
            "moveWS": {"command": "STOP", "weight": 1.0}  # 전차 정지
        }

    # -------------------------
    # 포탑이 90도 이상일 때
    # 플래그 설정 후 원형 이동 시작
    # -------------------------
    elif turret_x >= 90 and not myFlag:
        myFlag = True
        print("Turret locked at 90°, start circular motion")
        command = {
            "moveWS": {"command": "W", "weight": 0.3},   # 일정 속도 전진
            "moveAD": {"command": "D", "weight": 0.5},   # 우회전
            "turretQE": {"command": "", "weight": 0.0},  # 포탑 고정
            "fire": False
        }

    # -------------------------
    # 플래그가 True일 때
    # 포탑 고정, 전차 원형 이동 지속
    # -------------------------
    elif myFlag:
        command = {
            "moveWS": {"command": "W", "weight": 0.3},   # 일정 속도 전진
            "moveAD": {"command": "D", "weight": 0.5},   # 우회전 지속
            "turretQE": {"command": "", "weight": 0.0},  # 포탑 고정
            "fire": False
        }

    # 전송할 명령 출력 (디버그용)
    print("Sent Combined Action:", command)

    # 명령 반환
    return jsonify(command)


# -------------------------
# /init 엔드포인트
# 시뮬레이션 시작 시 초기 설정 값 반환
# -------------------------
@app.route('/init', methods=['GET'])
def init():
    config = {
        "startMode": "pause",  # 시뮬레이션 시작 모드: "start" 또는 "pause"
        "blStartX": 180,       # 아군 시작 위치 X
        "blStartY": 10,        # 아군 시작 위치 Y
        "blStartZ": 180,       # 아군 시작 위치 Z
        "rdStartX": 180,       # 적군 시작 위치 X
        "rdStartY": 10,        # 적군 시작 위치 Y
        "rdStartZ": 170,       # 적군 시작 위치 Z
        "trackingMode": True,  # 목표 추적 활성화
        "detactMode": False,   # 물체 감지 비활성화
        "logMode": False,      # 로그 저장 비활성화
        "enemyTracking": False,# 적 추적 비활성화
        "saveSnapshot": False, # 스냅샷 저장 비활성화
        "saveLog": False,      # 로그 저장 비활성화
        "saveLidarData": False,# 라이다 데이터 저장 비활성화
        "lux": 30000           # 조도 값
    }
    # 초기 설정 출력
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
# Flask 서버 실행
# -------------------------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=6000)
