
# OpenMP 중복 오류 임시 우회 (libiomp5md.dll)
import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

# Flask 웹 프레임워크와 필요한 모듈들을 import
from flask import Flask, request, jsonify
# PyTorch 딥러닝 프레임워크 import
import torch
# YOLO 객체 탐지 모델을 위한 ultralytics 라이브러리 import
from ultralytics import YOLO

# Flask 애플리케이션 인스턴스 생성
app = Flask(__name__)
# YOLO 모델 로드 (yolov8n.pt 파일 사용)
model = YOLO('yolov8n.pt')

# 미리 정의된 탱크 행동 명령어들의 조합 리스트
combined_commands = [
    {
        # 앞뒤 이동: W키로 앞으로 이동, 가중치 1.0 (최대 속도)
        "moveWS": {"command": "W", "weight": 1.0},
        # 좌우 이동: D키로 오른쪽 이동, 가중치 1.0 (최대 속도)
        "moveAD": {"command": "D", "weight": 1.0},
        # 포탑 좌우 회전: Q키로 왼쪽 회전, 가중치 0.7
        "turretQE": {"command": "Q", "weight": 0.7},
        # 포탑 상하 조준: R키로 위쪽 조준, 가중치 0.5
        "turretRF": {"command": "R", "weight": 0.5},
        # 발사 여부: False (발사하지 않음)
        "fire": False
    },
    {
        # 앞뒤 이동: W키로 앞으로 이동, 가중치 0.6 (중간 속도)
        "moveWS": {"command": "W", "weight": 0.6},
        # 좌우 이동: A키로 왼쪽 이동, 가중치 0.4
        "moveAD": {"command": "A", "weight": 0.4},
        # 포탑 좌우 회전: E키로 오른쪽 회전, 가중치 0.8
        "turretQE": {"command": "E", "weight": 0.8},
        # 포탑 상하 조준: R키로 위쪽 조준, 가중치 0.3
        "turretRF": {"command": "R", "weight": 0.3},
        # 발사 여부: True (발사함)
        "fire": True
    },
    {
        # 앞뒤 이동: W키로 앞으로 이동, 가중치 0.5 (중간 속도)
        "moveWS": {"command": "W", "weight": 0.5},
        # 좌우 이동: 명령어 없음 (좌우로 움직이지 않음)
        "moveAD": {"command": "", "weight": 0.0},
        # 포탑 좌우 회전: E키로 오른쪽 회전, 가중치 0.4
        "turretQE": {"command": "E", "weight": 0.4},
        # 포탑 상하 조준: R키로 위쪽 조준, 가중치 0.6
        "turretRF": {"command": "R", "weight": 0.6},
        # 발사 여부: False (발사하지 않음)
        "fire": False
    },
    {
        # 앞뒤 이동: W키로 앞으로 이동, 가중치 0.3 (느린 속도)
        "moveWS": {"command": "W", "weight": 0.3},
        # 좌우 이동: D키로 오른쪽 이동, 가중치 0.3
        "moveAD": {"command": "D", "weight": 0.3},
        # 포탑 좌우 회전: E키로 오른쪽 회전, 가중치 0.5
        "turretQE": {"command": "E", "weight": 0.5},
        # 포탑 상하 조준: R키로 위쪽 조준, 가중치 0.7
        "turretRF": {"command": "R", "weight": 0.7},
        # 발사 여부: True (발사함)
        "fire": True
    },
    {
        # 앞뒤 이동: W키로 앞으로 이동, 가중치 1.0 (최대 속도)
        "moveWS": {"command": "W", "weight": 1.0},
        # 좌우 이동: 명령어 없음 (좌우로 움직이지 않음)
        "moveAD": {"command": "", "weight": 0.0},
        # 포탑 좌우 회전: E키로 오른쪽 회전, 가중치 0.5
        "turretQE": {"command": "E", "weight": 0.5},
        # 포탑 상하 조준: R키로 위쪽 조준, 가중치 0.5
        "turretRF": {"command": "R", "weight": 0.5},
        # 발사 여부: False (발사하지 않음)
        "fire": False
    },
    {
        # 앞뒤 이동: W키로 앞으로 이동, 가중치 0.8 (빠른 속도)
        "moveWS": {"command": "W", "weight": 0.8},
        # 좌우 이동: A키로 왼쪽 이동, 가중치 0.6
        "moveAD": {"command": "A", "weight": 0.6},
        # 포탑 좌우 회전: E키로 오른쪽 회전, 가중치 0.9 (빠른 회전)
        "turretQE": {"command": "E", "weight": 0.9},
        # 포탑 상하 조준: R키로 위쪽 조준, 가중치 0.2 (느린 조준)
        "turretRF": {"command": "R", "weight": 0.2},
        # 발사 여부: True (발사함)
        "fire": True
    },
    {
        # 앞뒤 이동: W키로 앞으로 이동, 가중치 1.0 (최대 속도)
        "moveWS": {"command": "W", "weight": 1.0},
        # 좌우 이동: D키로 오른쪽 이동, 가중치 1.0 (최대 속도)
        "moveAD": {"command": "D", "weight": 1.0},
        # 포탑 좌우 회전: E키로 오른쪽 회전, 가중치 1.0 (최대 회전속도)
        "turretQE": {"command": "E", "weight": 1.0},
        # 포탑 상하 조준: R키로 위쪽 조준, 가중치 1.0 (최대 조준속도)
        "turretRF": {"command": "R", "weight": 1.0},
        # 발사 여부: True (발사함)
        "fire": True
    },
    {
        # 앞뒤 이동: W키로 앞으로 이동, 가중치 0.2 (매우 느린 속도)
        "moveWS": {"command": "W", "weight": 0.2},
        # 좌우 이동: A키로 왼쪽 이동, 가중치 0.9 (빠른 속도)
        "moveAD": {"command": "A", "weight": 0.9},
        # 포탑 좌우 회전: 명령어 없음 (포탑을 회전하지 않음)
        "turretQE": {"command": "", "weight": 0.0},
        # 포탑 상하 조준: R키로 위쪽 조준, 가중치 0.9 (빠른 조준)
        "turretRF": {"command": "R", "weight": 0.9},
        # 발사 여부: False (발사하지 않음)
        "fire": False
    },
    {
        # 앞뒤 이동: S키로 뒤로 이동, 가중치 0.4
        "moveWS": {"command": "S", "weight": 0.4},
        # 좌우 이동: D키로 오른쪽 이동, 가중치 0.4
        "moveAD": {"command": "D", "weight": 0.4},
        # 포탑 좌우 회전: E키로 오른쪽 회전, 가중치 0.6
        "turretQE": {"command": "E", "weight": 0.6},
        # 포탑 상하 조준: F키로 아래쪽 조준, 가중치 0.6
        "turretRF": {"command": "F", "weight": 0.6},
        # 발사 여부: True (발사함)
        "fire": True
    },
    {
        # 앞뒤 이동: W키로 앞으로 이동, 가중치 0.8 (빠른 속도)
        "moveWS": {"command": "W", "weight": 0.8},
        # 좌우 이동: 명령어 없음 (좌우로 움직이지 않음)
        "moveAD": {"command": "", "weight": 0.0},
        # 포탑 좌우 회전: Q키로 왼쪽 회전, 가중치 0.5
        "turretQE": {"command": "Q", "weight": 0.5},
        # 포탑 상하 조준: 명령어 없음 (상하로 조준하지 않음)
        "turretRF": {"command": "", "weight": 0.0},
        # 발사 여부: False (발사하지 않음)
        "fire": False
    },
    {
        # 앞뒤 이동: STOP 명령으로 정지, 가중치 1.0
        "moveWS": {"command": "STOP", "weight": 1.0},
        # 좌우 이동: 명령어 없음 (좌우로 움직이지 않음)
        "moveAD": {"command": "", "weight": 0.0},
        # 포탑 좌우 회전: 명령어 없음 (포탑을 회전하지 않음)
        "turretQE": {"command": "", "weight": 0.0},
        # 포탑 상하 조준: 명령어 없음 (상하로 조준하지 않음)
        "turretRF": {"command": "", "weight": 0.0},
        # 발사 여부: True (발사함) - 정지한 상태에서 발사
        "fire": True
    },
    {
        # 앞뒤 이동: S키로 뒤로 이동, 가중치 0.2 (매우 느린 속도)
        "moveWS": {"command": "S", "weight": 0.2},
        # 좌우 이동: A키로 왼쪽 이동, 가중치 0.2 (매우 느린 속도)
        "moveAD": {"command": "A", "weight": 0.2},
        # 포탑 좌우 회전: E키로 오른쪽 회전, 가중치 0.2 (매우 느린 회전)
        "turretQE": {"command": "E", "weight": 0.2},
        # 포탑 상하 조준: F키로 아래쪽 조준, 가중치 0.2 (매우 느린 조준)
        "turretRF": {"command": "F", "weight": 0.2},
        # 발사 여부: False (발사하지 않음)
        "fire": False
    }
# 명령어 리스트 종료
]


# 객체 탐지를 위한 Flask 라우트 (/detect 엔드포인트)
@app.route('/detect', methods=['POST'])
def detect():
    # 요청에서 이미지 파일 가져오기
    image = request.files.get('image')
    # 이미지가 없으면 에러 응답 반환
    if not image:
        return jsonify({"error": "No image received"}), 400

    # 임시 이미지 파일 경로 설정
    image_path = 'temp_image.jpg'
    # 이미지를 임시 파일로 저장
    image.save(image_path)

    # YOLO 모델로 이미지 객체 탐지 실행
    results = model(image_path)
    # 탐지 결과에서 바운딩 박스 데이터를 CPU로 이동하고 numpy 배열로 변환
    detections = results[0].boxes.data.cpu().numpy()

    # 탐지할 대상 클래스 정의 (클래스 ID: 클래스 이름)
    target_classes = {0: "person", 2: "car", 7: "truck", 15: "rock"}
    # 필터링된 결과를 저장할 리스트
    filtered_results = []
    # 각 탐지된 객체에 대해 반복
    for box in detections:
        # 클래스 ID 추출 (정수형으로 변환)
        class_id = int(box[5])
        # 대상 클래스에 포함되는지 확인
        if class_id in target_classes:
            # 결과 딕셔너리에 탐지 정보 추가
            filtered_results.append({
                # 클래스 이름
                'className': target_classes[class_id],
                # 바운딩 박스 좌표 [x1, y1, x2, y2]
                'bbox': [float(coord) for coord in box[:4]],
                # 신뢰도 점수
                'confidence': float(box[4]),
                # 바운딩 박스 색상 (녹색)
                'color': '#00FF00',
                # 바운딩 박스 채우기 여부
                'filled': True,
                # 이동 중 박스 업데이트 여부
                'updateBoxWhileMoving': True
            })

    # 필터링된 탐지 결과를 JSON으로 반환
    return jsonify(filtered_results)

# 정보 수신을 위한 Flask 라우트 (/info 엔드포인트)
@app.route('/info', methods=['POST'])
def info():
    # 요청에서 JSON 데이터 강제로 가져오기
    data = request.get_json(force=True)
    # 데이터가 없으면 에러 응답 반환
    if not data:
        return jsonify({"error": "No JSON received"}), 400

    # 수신된 데이터를 콘솔에 출력 (주석 처리됨)
    #print("📨 /info data received:", data)

    # 15초 후 자동 일시정지 (주석 처리됨)
    #if data.get("time", 0) > 15:
    #    return jsonify({"status": "success", "control": "pause"})
    # 15초 후 자동 리셋 (주석 처리됨)
    #if data.get("time", 0) > 15:
    #    return jsonify({"stsaatus": "success", "control": "reset"})
    # 성공 상태와 빈 제어 명령어 반환
    return jsonify({"status": "success", "control": ""})

# 행동 명령어 제공을 위한 Flask 라우트 (/get_action 엔드포인트)
@app.route('/get_action', methods=['POST'])
def get_action():
    # 요청에서 JSON 데이터 강제로 가져오기
    data = request.get_json(force=True)

    # 위치 정보 추출 (기본값: 빈 딕셔너리)
    position = data.get("position", {})
    # 포탑 정보 추출 (기본값: 빈 딕셔너리)
    turret = data.get("turret", {})

    # 위치의 x, y, z 좌표 추출 (기본값: 0)
    pos_x = position.get("x", 0)
    pos_y = position.get("y", 0)
    pos_z = position.get("z", 0)

    # 포탑의 x, y 각도 추출 (기본값: 0)
    turret_x = turret.get("x", 0)
    turret_y = turret.get("y", 0)

    # 수신된 위치 정보를 콘솔에 출력
    print(f"📨 Position received: x={pos_x}, y={pos_y}, z={pos_z}")
    # 수신된 포탑 정보를 콘솔에 출력
    print(f"🎯 Turret received: x={turret_x}, y={turret_y}")

    # 미리 정의된 명령어가 남아있는지 확인
    if combined_commands:
        # 리스트에서 첫 번째 명령어를 제거하고 반환
        command = combined_commands.pop(0)
    else:
        # 명령어가 없으면 기본 정지 명령어 사용
        command = {
            "moveWS": {"command": "STOP", "weight": 1.0},
            "moveAD": {"command": "", "weight": 0.0},
            "turretQE": {"command": "", "weight": 0.0},
            "turretRF": {"command": "", "weight": 0.0},
            "fire": False
        }

    # 전송할 명령어를 콘솔에 출력
    print("🔁 Sent Combined Action:", command)
    # 명령어를 JSON으로 반환
    return jsonify(command)

# 총알 업데이트 정보 수신을 위한 Flask 라우트 (/update_bullet 엔드포인트)
@app.route('/update_bullet', methods=['POST'])
def update_bullet():
    # 요청에서 JSON 데이터 가져오기
    data = request.get_json()
    # 데이터가 없으면 에러 응답 반환
    if not data:
        return jsonify({"status": "ERROR", "message": "Invalid request data"}), 400

    # 총알 충돌 정보를 콘솔에 출력 (위치와 적중 여부)
    print(f"💥 Bullet Impact at X={data.get('x')}, Y={data.get('y')}, Z={data.get('z')}, Target={data.get('hit')}")
    # 성공 응답 반환
    return jsonify({"status": "OK", "message": "Bullet impact data received"})

# 목적지 설정을 위한 Flask 라우트 (/set_destination 엔드포인트)
@app.route('/set_destination', methods=['POST'])
def set_destination():
    # 요청에서 JSON 데이터 가져오기
    data = request.get_json()
    # 데이터가 없거나 destination 키가 없으면 에러 응답 반환
    if not data or "destination" not in data:
        return jsonify({"status": "ERROR", "message": "Missing destination data"}), 400

    try:
        # destination 문자열을 쉼표로 분리하여 x, y, z 좌표로 변환
        x, y, z = map(float, data["destination"].split(","))
        # 설정된 목적지를 콘솔에 출력
        print(f"🎯 Destination set to: x={x}, y={y}, z={z}")
        # 성공 응답과 함께 목적지 좌표 반환
        return jsonify({"status": "OK", "destination": {"x": x, "y": y, "z": z}})
    except Exception as e:
        # 좌표 변환 실패 시 에러 응답 반환
        return jsonify({"status": "ERROR", "message": f"Invalid format: {str(e)}"}), 400

# 시각화 모듈 import
from pattern_graph import visualize_obstacle_pattern, print_pattern_analysis

# 장애물 업데이트 정보 수신을 위한 Flask 라우트 (/update_obstacle 엔드포인트)
@app.route('/update_obstacle', methods=['POST'])
def update_obstacle():
    # 요청에서 JSON 데이터 가져오기
    data = request.get_json()
    # 데이터가 없으면 에러 응답 반환
    if not data:
        return jsonify({'status': 'error', 'message': 'No data received'}), 400

    # 수신된 장애물 데이터를 콘솔에 출력
    print("🪨 Obstacle Data:", data)
    
    # 장애물이 9개일 때 처리 로직 실행
    obstacles = data.get('obstacles', [])
    if len(obstacles) == 9:
        print("\n🔄 9개 장애물 감지! 그룹 분류 및 정렬 시작...")
        
        # 1. group1에 9개 장애물 저장
        group1 = obstacles.copy()
        
        # 2. z_max 기준으로 그룹 분류
        a_group = []  # z_max <= 100
        b_group = []  # 100 < z_max <= 200  
        c_group = []  # z_max > 200
        
        for obstacle in group1:
            z_max = obstacle['z_max']
            if z_max <= 100:
                a_group.append(obstacle)
            elif z_max <= 200:
                b_group.append(obstacle)
            else:
                c_group.append(obstacle)
        
        print(f"📊 그룹 분류 결과: A그룹({len(a_group)}개), B그룹({len(b_group)}개), C그룹({len(c_group)}개)")
        
        # 5. a_group, c_group: x_max 오름차순 정렬
        a_group.sort(key=lambda x: x['x_max'])
        c_group.sort(key=lambda x: x['x_max'])
        
        # 6. b_group: x_max 내림차순 정렬  
        b_group.sort(key=lambda x: x['x_max'], reverse=True)
        
        # 7. group2 생성 (a_group + b_group + c_group 순서)
        group2 = a_group + b_group + c_group
        
        # 8. 좌표 한개씩 출력
        print("\n📋 최종 정렬된 장애물 좌표:")
        for i, obstacle in enumerate(group2, 1):
            print(f"  {i}번: x_min={obstacle['x_min']:.2f}, x_max={obstacle['x_max']:.2f}, "
                  f"z_min={obstacle['z_min']:.2f}, z_max={obstacle['z_max']:.2f}")
        
        # 9. 시각화 실행
        print("\n🎨 장애물 패턴 시각화 생성 중...")
        try:
            visualize_obstacle_pattern(obstacles)
            print_pattern_analysis(group2)
        except Exception as e:
            print(f"⚠️ 시각화 오류: {e}")
        
        print("✅ 장애물 처리 완료!\n")
    
    # 성공 응답 반환
    return jsonify({'status': 'success', 'message': 'Obstacle data received'})

# 충돌 감지 정보 수신을 위한 Flask 라우트 (/collision 엔드포인트)
@app.route('/collision', methods=['POST']) 
def collision():
    # 요청에서 JSON 데이터 가져오기
    data = request.get_json()
    # 데이터가 없으면 에러 응답 반환
    if not data:
        return jsonify({'status': 'error', 'message': 'No collision data received'}), 400

    # 충돌한 객체 이름 추출
    object_name = data.get('objectName')
    # 충돌 위치 정보 추출 (기본값: 빈 딕셔너리)
    position = data.get('position', {})
    # 위치의 x, y, z 좌표 추출
    x = position.get('x')
    y = position.get('y')
    z = position.get('z')

    # 충돌 감지 정보를 콘솔에 출력
    print(f"💥 Collision Detected - Object: {object_name}, Position: ({x}, {y}, {z})")

    # 성공 응답 반환
    return jsonify({'status': 'success', 'message': 'Collision data received'})

# 에피소드 시작 시 호출되는 초기화 엔드포인트
@app.route('/init', methods=['GET'])
def init():
    # 초기 설정 구성 딕셔너리
    config = {
        # 시작 모드: "start" 또는 "pause"
        "startMode": "start",  # Options: "start" or "pause"
        # 블루팀 시작 위치 X 좌표
        "blStartX": 60,  #Blue Start Position
        # 블루팀 시작 위치 Y 좌표
        "blStartY": 10,
        # 블루팀 시작 위치 Z 좌표
        "blStartZ": 27.23,
        # 레드팀 시작 위치 X 좌표
        "rdStartX": 59, #Red Start Position
        # 레드팀 시작 위치 Y 좌표
        "rdStartY": 10,
        # 레드팀 시작 위치 Z 좌표
        "rdStartZ": 280,
        # 추적 모드 활성화 여부
        "trackingMode": True,
        # 탐지 모드 활성화 여부
        "detactMode": False,
        # 로그 모드 활성화 여부
        "logMode": True,
        # 적 추적 기능 활성화 여부
        "enemyTracking": True,
        # 스냅샷 저장 여부
        "saveSnapshot": False,
        # 로그 저장 여부
        "saveLog": True,
        # 라이다 데이터 저장 여부
        "saveLidarData": False,
        # 조명 밝기 설정
        "lux": 30000
    }
    # 초기화 설정을 콘솔에 출력
    print("🛠️ Initialization config sent via /init:", config)
    # 설정을 JSON으로 반환
    return jsonify(config)

@app.route('/start', methods=['GET'])
def start():
    # print("🚀 /start command received")
    return jsonify({"control": ""})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

