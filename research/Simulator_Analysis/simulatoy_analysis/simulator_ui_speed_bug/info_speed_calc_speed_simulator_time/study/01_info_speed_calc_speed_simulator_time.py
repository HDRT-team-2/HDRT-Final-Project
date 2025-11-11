"""
목적: info의 tank_speed와 status의 tank_speed 값이 서로 다르게 나타남에 따라,  
info에서 제공하는 시간 값(time)과 player_x, player_z 좌표를 활용하여 거리를 계산한 뒤,  
속도 = 거리 / 시간 공식을 이용해 실제 속도를 측정하였다.  

이렇게 계산된 속도와 info에서의 player_speed(tank_speed), 그리고 status에서의 speed 값을 비교하여  
어느 쪽이 올바른 값을 나타내는지 검증하기 위한 실험이다.
"""

from flask import Flask, request, jsonify  # Flask 웹 서버 구축 및 요청/응답(JSON) 처리용
import math  # 수학 계산(거리, 각도 등)용 기본 모듈

_prev_x = None  # 이전 x좌표 저장
_prev_z = None  # 이전 z좌표 저장
_prev_t = None  # 이전 시간(time) 저장


# -------------------------------------------------------------------
# detect | Integrated Battlefield Situation Management (IBSM)
enemy_detection, enemy_in_fov = False, False # detect API

# info, get_action | Tank Turret Rotation Control
global_QE_command, global_QE_weight, global_RF_command, global_RF_weight = "", 0.0, "", 0.0
# info, get_action | Tank Body Movement Control
global_WS_command, global_WS_weight, global_AD_command, global_AD_weight = "", 0.0, "", 0.0
# info, get_action | Tank Fire Control
global_fire_command = False

# -------------------------------------------------------------------

# info | Waypoint : Linked List
class WaypointNode:
    def __init__(self, x, z):
        self.x = float(x) # pos x
        self.z = float(z) # pos y 
        self.next = None # next node

class WaypointList:
    def __init__(self):
        self.head = None # head node (first waypoint)
        self.tail = None # tail node (last waypoint)
        self._len = 0 # length (number of waypoints)

    def append(self, x, z):
        # Add a new waypoint to the end of the list
        node = WaypointNode(x, z)
        if not self.head:
            self.head = self.tail = node # If list is empty, set head and tail
        else:
            self.tail.next = node # Link new node to the end
            self.tail = node      # Update tail to new node
        self._len += 1
        return node
    
    def peek(self):
        # Return the first waypoint (head) without removing it
        return self.head

    def pop(self):
        # Remove and return the first waypoint (head)
        if not self.head:
            return None
        node = self.head
        self.head = node.next
        if not self.head:
            self.tail = None # If list is now empty, reset tail
        node.next = None
        self._len -= 1
        return node

    def is_empty(self):
        # Check if the waypoint list is empty
        return self.head is None

    def to_list(self):
        # Convert the linked list of waypoints to a Python list of dicts
        out = []
        cur = self.head
        while cur:
            out.append({'x': cur.x, 'z': cur.z})
            cur = cur.next
        return out

# --------------------------------------------------------------------

# Path Planning
waypoints = WaypointList()

# for idx, y in enumerate(range(5, 296, 5)): # whole path waypoints
#     if idx % 2 == 0:
#         waypoints.append(5, y)
#         waypoints.append(295, y)
#     else:
#         waypoints.append(295, y)
#         waypoints.append(5, y)


def generate_circle_nodes(x, y, z, num_nodes, radius):  #y는 좌표입력 혼동방지를 위한 더미데이터(top view 기준의 2차원 좌표이기에, y값은 안쓰임.)
    nodes = []                                  # 출력할 좌표들을 저장할 리스트

    for i in range(num_nodes):
        angle = 2 * math.pi * i / num_nodes     # 원을 라디안 단위 각도로 노드 갯수 만큼 나눔
        px = x + radius * math.cos(angle)       # x좌표 생성
        pz = z + radius * math.sin(angle)       # z좌표 생성
        nodes.append((px, pz))                  # 생성한 x,z좌표를 리스트에 저장

    return nodes

# Generate waypoints from the generated circle nodes
nodes = generate_circle_nodes(150, 10, 150, num_nodes = 8, radius = 100) # x, y, z 좌표, 노드 갯수(짝수로 입력할것!), 반지름 넓이
for i in range(len(nodes)): 
    waypoints.append(nodes[i][0], nodes[i][1])      # 웨이포인트에 생성된 좌표들 주입

print(waypoints.to_list())                          # 웨이포인트에 generate_circle_nodes가 만든 좌표들이 정상적으로 주입되었는지 확인용

# --------------------------------------------------------------------

def path_finding(): # 경로 탐색 함수
    # not yet
    path = waypoints
    return path

def path_tracking(player_x, player_z, player_body_x, player_speed): # 경로 추적 함수
    print("path_tracking")
    # 커맨드 초기화
    WS_command, WS_weight, AD_command, AD_weight = "", 0.0, "", 0.0

    # path: 여러 개의 웨이포인트로 구성된 경로
    # 초기: 단순 웨이포인트 추적 로직
    # 중장기: 코너링에 대한 Catmull-Rom Spline 보간을 통해 부드러운 경로 생성 및 추적으로 할지

    # (도착 판단 및 웨이포인트 교체)1. 현재 웨이포인트 선택 및 도달 여부 확인
    while True:
        current_waypoint = waypoints.peek()
        print("\n\n\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!peek!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n\n\n")
        if current_waypoint is None:
            # 웨이포인트가 없으면 정지
            WS_command, WS_weight = "STOP", 1.0
            AD_command, AD_weight = "", 0.0
            return WS_command, WS_weight, AD_command, AD_weight
        distance = math.sqrt((current_waypoint.x - player_x)**2 + (current_waypoint.z - player_z)**2)
        print("Distance to Waypoint:", distance)
        # 도착 판단: 웨이포인트에 1.0 미터 이내로 접근했으면 도달한 것으로 간주
        if distance <= 1.0:
            print("\n\n\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!REACHED WAYPOINT!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n\n\n")
            WS_command, WS_weight = "STOP", 1.0
            AD_command, AD_weight = "", 0.0
            waypoints.pop() # 다음 웨이포인트로 교체
            return WS_command, WS_weight, AD_command, AD_weight
        
        # 만약 웨이포인트에 도달하지 않았으면, 루프 탈출
        break

    print("현재 향하는 웨이포인트:", current_waypoint.x, current_waypoint.z)
    # (회전)1. 현재 탱크 위치와 웨이포인트 간의 수평각 계산
    dx = current_waypoint.x - player_x
    dz = current_waypoint.z - player_z
    target_angle = math.degrees(math.atan2(dx, dz)) % 360
    # print("Target Angle:", target_angle)

    # (회전)2. 현재 탱크의 수직각, 수평각을 확인하여 웨이포인트 방향으로 회전 명령 생성
    # - 전속력(weight = 1.0) 회전 수행
    # - 만약, 탱크의 수평각이 목표 수평각보다 5도 이내로 들어오면, 회전 명령 중지
    angle_diff = abs(player_body_x - target_angle)
    # print("Angle Diff:", angle_diff)
    if angle_diff > 20:
        
        if (player_body_x - target_angle + 360) % 360 > 180:
            AD_command, AD_weight = "D", 1.0
            # print("Rotate D 1.0")
        else:
            AD_command, AD_weight = "A", 1.0
            # print("Rotate A 1.0")

    # (회전) 3. 회전 명령 중지 후, 만약, 탱크의 수평각이 목표 수평각보다 1도 이상 크거나, 작으면, 반대로 역 조정 명령 생성
    elif angle_diff > 0.8:
        AD_command, AD_weight = "", 0.0 # 명령 초기화
        if player_body_x - target_angle > 0.5:
            # print("Rotate A 0.05")
            AD_command, AD_weight = "A", 0.05
        elif player_body_x - target_angle < -0.5:
            # print("Rotate D 0.05")
            AD_command, AD_weight = "D", 0.05
    # (회전) 4. 만약, 탱크의 회전각이 웨이포인트 방향과 일치하면, 저속 전진 명령 생성
    elif angle_diff <= 0.8:
        WS_command, WS_weight = "W", 0.3
        # print("Move W 0.3")

    return WS_command, WS_weight, AD_command, AD_weight

def stabilizer(player_x, player_y, player_z, player_turret_x, player_turret_y, enemy_x, enemy_y, enemy_z):
    QE_command, QE_weight, RF_command, RF_weight = "", 0.0, "", 0.0
    
    # 반환: QE/RF 터렛 명령과 가중치

    # 아군과 적 전차 간 상대 위치 계산
    dx = enemy_x - player_x  # X축 차이
    dz = enemy_z - player_z  # Z축 차이
    dy = enemy_y - player_y  # Y축 차이 (높이)

    # XZ 평면 거리 계산
    distance_xz = math.hypot(dx, dz)
    target_pitch = math.degrees(math.atan2(dy, distance_xz))  # 포신 상하 각도

    # 목표 yaw 계산 (터렛 좌/우 회전 각도)
    yaw_rad = math.atan2(dx, dz)
    target_yaw = math.degrees(yaw_rad)
    if target_yaw < 0:
        target_yaw += 360  # 음수 보정

    # --- 터렛 Q/E 회전 명령 계산 ---
    yaw_angle_diff = (target_yaw - player_turret_x + 540) % 360 - 180  # -180 ~ 180도 범위로 정규화
    if abs(yaw_angle_diff) > 1.0:  # 오차 1도 이상일 때만 회전
        QE_command = "Q" if yaw_angle_diff < 0 else "E"  # 좌/우 선택
        QE_weight = 1.0 if abs(yaw_angle_diff) >= 20.0 else 0.15  # 가중치 (큰 차이면 강하게)

    # --- 터렛 R/F 회전 명령 계산 ---
    pitch_angle_diff = target_pitch - player_turret_y  # 목표 pitch와 현재 터렛 pitch 차이
    if abs(pitch_angle_diff) > 1.0:  # 오차 1도 이상
        RF_command = "R" if pitch_angle_diff > 0 else "F"  # 상/하 선택
        RF_weight = 1.0 if abs(pitch_angle_diff) >= 10.0 else 0.1  # 가중치

    return QE_command, QE_weight, RF_command, RF_weight


def fire_calculation(): # 사격 계산 함수
    QE_command, QE_weight, RF_command, RF_weight, fire_command = 0.0, 0.0, 0.0, 0.0, False
    return QE_command, QE_weight, RF_command, RF_weight, fire_command

def turret_control(enemy_detection, enemy_in_fov, player_x, player_y, player_z, player_turret_x, player_turret_y, enemy_x, enemy_y, enemy_z): # 포탑 제어 함수
    print("turret_control")
    # 초기화
    QE_command, QE_weight, RF_command, RF_weight, fire_command = 0.0, 0.0, 0.0, 0.0, False
    enemy_detection, enemy_in_fov = True, False # 테스트용 적 탐지 플래그

    if enemy_detection == True and enemy_in_fov == False: # 적이 탐지되었지만, 시야에 없는 경우
        print("Stabilizer Active")
        QE_command, QE_weight, RF_command, RF_weight = stabilizer(player_x, player_y, player_z, player_turret_x, player_turret_y, enemy_x, enemy_y, enemy_z) # 스테빌 라이저로 마지막으로 포착된 적 위치에 조준 안정화

    elif enemy_detection == True and enemy_in_fov == True: # 적이 탐지되고, 시야에 있는 경우
        QE_command, QE_weight, RF_command, RF_weight, fire_command = fire_calculation() # 사격 계산 수행하여 조준 및 사격 명령

    return QE_command, QE_weight, RF_command, RF_weight, fire_command

def body_control(player_x, player_z, player_body_x, player_speed): # 차체 제어 함수
    print("body_control")
    # path = path_finding() # 경로 탐색 함수
    path = waypoints # 수동 경로 할당

    WS_command, WS_weight, AD_command, AD_weight = path_tracking(player_x, player_z, player_body_x, player_speed)
    
    return WS_command, WS_weight, AD_command, AD_weight

# --------------------------------------------------------------------

app = Flask(__name__) # Flask 앱 생성
# --------------------------------------------------------------------

@app.route('/info', methods=['POST'])  # 클라이언트(시뮬레이터)가 전차 상태 정보를 주기적으로 전송하는 엔드포인트
def info():
    # --- 전역 변수 선언 ---
    # turret 제어 관련 (포탑 회전, 사격 등)
    global global_QE_command, global_QE_weight, global_RF_command, global_RF_weight
    # body 제어 관련 (전차의 전후진, 좌우 회전 등)
    global global_WS_command, global_WS_weight, global_AD_command, global_AD_weight
    # 사격 명령
    global global_fire_command
    # 탐지 상태 (적 감지 여부, 시야 내 존재 여부)
    global enemy_detection, enemy_in_fov
    # 이전 프레임의 좌표(x, z) 및 시간 저장용 변수
    global _prev_x, _prev_z, _prev_t

    # --------------------------------------------------------------------
    # 클라이언트로부터 JSON 형식의 데이터 수신
    # --------------------------------------------------------------------
    data = request.get_json(force=True)  # 요청(request) body를 JSON으로 파싱
    if not data:  # 데이터가 비어 있을 경우
        return jsonify({"error": "No JSON received"}), 400  # 오류 응답 반환 (HTTP 400: 잘못된 요청)

    # --------------------------------------------------------------------
    # 받은 데이터에서 주요 변수 추출
    # --------------------------------------------------------------------
    time = data["time"]             # 시뮬레이션 시간 (초 단위)
    distance = data["distance"]     # 이동 거리 또는 경로 거리 정보 (필요 시 사용)

    # --- 아군 전차(player) 정보 ---
    player_x = data["playerPos"]["x"]
    player_y = data["playerPos"]["y"]
    player_z = data["playerPos"]["z"]

    player_speed = data["playerSpeed"]          # 전차 속도 (status에서 측정된 속도)
    player_health = data["playerHealth"]        # 전차 체력
    player_turret_x = data["playerTurretX"]     # 포탑 yaw 각도
    player_turret_y = data["playerTurretY"]     # 포탑 pitch 각도
    player_body_x = data["playerBodyX"]         # 차체 yaw 각도
    player_body_y = data["playerBodyY"]         # 차체 pitch (보통 거의 0)
    player_body_z = data["playerBodyZ"]         # 차체 roll (필요 시 사용)

    # --- 적 전차(enemy) 정보 ---
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

    # --------------------------------------------------------------------
    # 포탑 제어 로직 호출
    # turret_control() → 적의 위치를 기반으로 포탑 회전 및 사격 여부 결정
    # --------------------------------------------------------------------
    global_QE_command, global_QE_weight, global_RF_command, global_RF_weight, global_fire_command = \
        turret_control(enemy_detection, enemy_in_fov,
                       player_x, player_y, player_z,
                       player_turret_x, player_turret_y,
                       enemy_x, enemy_y, enemy_z)

    # --------------------------------------------------------------------
    # 차체(body) 제어 로직 호출
    # body_control() → 현재 위치, 속도, 방향을 기반으로 이동 명령 계산
    # --------------------------------------------------------------------
    global_WS_command, global_WS_weight, global_AD_command, global_AD_weight = \
        body_control(player_x, player_z, player_body_x, player_speed)

    # --------------------------------------------------------------------
    # 속도 계산 (info 데이터의 좌표/시간 기반으로 직접 계산)
    #  → status에서 주는 속도(player_speed)와 비교 실험용
    # --------------------------------------------------------------------
    calc_speed_ms = None  # 새로 계산된 속도 (m/s 단위)

    if _prev_t is not None:  # 이전 프레임이 존재할 경우에만 계산 수행
        dt = time - _prev_t  # 시간 차이(Δt, 초 단위)
        print("시간 차:", dt)

        if dt > 0:  # Δt가 0보다 커야 유효한 계산
            # 2D 거리 계산 (피타고라스 정리)
            dd = math.hypot(player_x - _prev_x, player_z - _prev_z)
            print("거리 차:", dd)
            print("시간 차:", dt)
            v_m_s = dd / dt  # 속도 = 거리 / 시간
            calc_speed_ms = v_m_s

    # 현재 위치와 시간을 다음 호출을 위해 저장
    _prev_x, _prev_z, _prev_t = player_x, player_z, time

    # --------------------------------------------------------------------
    # 결과 로그 출력
    # --------------------------------------------------------------------
    print("실제로 거리/시간으로 계산한 속도:", calc_speed_ms, "m/s")
    print("탱크 status에서의 속도:", player_speed, "m/s")  # info API에서 수신한 속도값

    # --------------------------------------------------------------------
    # 클라이언트에게 성공 응답 반환
    # --------------------------------------------------------------------
    return jsonify({"status": "success", "control": ""})

# --------------------------------------------------------------------

@app.route('/get_action', methods=['POST'])  # 클라이언트(시뮬레이터)가 행동 명령을 요청하는 엔드포인트
def get_action():
    # ------------------------------------------------------------
    # 전역 변수 선언 (info()에서 계산된 제어 명령을 불러오기 위해)
    # ------------------------------------------------------------
    global global_QE_command, global_QE_weight, global_RF_command, global_RF_weight  # 포탑 제어 관련 (turret)
    global global_WS_command, global_WS_weight, global_AD_command, global_AD_weight  # 차체 제어 관련 (body)
    global global_fire_command  # 사격 제어 명령 (True/False)

    # ------------------------------------------------------------
    # 이전 단계(info, control 함수 등)에서 계산된 전역 제어 변수를 기반으로
    #     현재 프레임에서 실행할 행동(Action)을 구성
    # ------------------------------------------------------------
    action = {
        # moveWS → 전후진 명령 (W: 전진, S: 후진)
        # 여기서는 항상 "W" 명령과 weight 1.0으로 설정되어 전진 상태를 유지함
        "moveWS":  {"command": "W", "weight": 1.0},  # ← 필요 시 가중치 조절 가능 (0.0 ~ 1.0)

        # moveAD → 좌우 회전 명령 (A: 좌회전, D: 우회전)
        # body_control()에서 계산된 전차 방향 제어 명령을 사용
        "moveAD":  {"command": global_AD_command, "weight": global_AD_weight},

        # turretQE → 포탑의 좌우 회전 제어 (Q: 좌, E: 우)
        # turret_control() 함수에서 계산된 포탑 회전 명령을 그대로 반영
        "turretQE": {"command": global_QE_command, "weight": global_QE_weight},

        # turretRF → 포탑의 상하 제어 (R: 상, F: 하)
        # turret_control() 함수에서 계산된 상하 움직임 명령 반영
        "turretRF": {"command": global_RF_command, "weight": global_RF_weight},

        # fire → 사격 명령 (True: 발사, False: 대기)
        # turret_control() 결과에 따라 자동 또는 조건부 발사
        "fire": global_fire_command
    }

    # ------------------------------------------------------------
    # JSON 응답으로 action 딕셔너리를 반환
    #   → 클라이언트(시뮬레이터)는 이 데이터를 수신해 실제 전차 움직임에 반영함
    # ------------------------------------------------------------
    return jsonify(action)


# --------------------------------------------------------------------

#Endpoint called when the episode starts
@app.route('/init', methods=['GET'])
def init():
    config = {
        "startMode": "start",  # Options: "start" or "pause"
        "blStartX": 0,  #Blue Start Position
        "blStartY": 10,
        "blStartZ": 0,
        "rdStartX": 300, #Red Start Position
        "rdStartY": 10,
        "rdStartZ": 150,
        "trackingMode": True,
        "detactMode": False,
        "logMode": True,
        "enemyTracking": False,
        "saveSnapshot": False,
        "saveLog": True,
        "saveLidarData": False,
        "lux": 30000
    }
    print("🛠️ Initialization config sent via /init:", config)
    return jsonify(config)

# --------------------------------------------------------------------

@app.route('/start', methods=['GET'])
def start():
    print("🚀 /start command received")
    return jsonify({"control": ""})

# --------------------------------------------------------------------

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

# --------------------------------------------------------------------
