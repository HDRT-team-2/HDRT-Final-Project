from flask import Flask, request, jsonify
import math
import matplotlib.pyplot as plt
import numpy as np
import os

# -------------------------------------------------------------------
# detect | Integrated Battlefield Situation Management (IBSM)
enemy_detection, enemy_in_fov = False, False # detect API

# info, get_action | Tank Turret Rotation Control
global_QE_command, global_QE_weight, global_RF_command, global_RF_weight = "", 0.0, "", 0.0
# info, get_action | Tank Body Movement Control
global_WS_command, global_WS_weight, global_AD_command, global_AD_weight = "", 0.0, "", 0.0
# info, get_action | Tank Fire Control
global_fire_command = False

# rotate flag: temporary
left_flag = False # 차체 좌측 회전 시 True, 회전 정지 시 False
right_flag = False # 차체 우측 회전 시 True, 회전 정지 시 False

# -------------------------------------------------------------------

# info | Waypoint : Linked List
class WaypointNode:
    def __init__(self, x, z, target_x, target_z):
        self.x = float(x) # pos x
        self.z = float(z) # pos y 
        self.target_x = float(target_x)
        self.target_z = float(target_z)
        self.next = None # next node

class WaypointList:
    def __init__(self):
        self.head = None # head node (first waypoint)
        self.tail = None # tail node (last waypoint)
        self._len = 0 # length (number of waypoints)

    def append(self, x, z, target_x, target_z):
        # Add a new waypoint to the end of the list
        node = WaypointNode(x, z, target_x, target_z)
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
            out.append({'x': cur.x, 'z': cur.z, 'target_x': cur.target_x, 'target_z': cur.target_z})
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

def generate_circle_nodes(x, z, num_nodes, radius, start_pos_angle, reverse):
    ### 각 증분(라디안)
    if reverse == True:     # 반시계 회전 여부가 True일 경우 : 
        delta = 2 * math.pi / num_nodes   #원을 한 바퀴(2π 라디안) 도는 각도를 num_nodes 개로 나눈 증분각 계산(반시계방향)
    else:                   # 반시계 회전 여부가 False일 경우 : 
        delta = -2 * math.pi / num_nodes  #원을 한 바퀴(2π 라디안) 도는 각도를 num_nodes 개로 나눈 증분각 계산(시계방향)

    ### 시작각/증분각의 sin,cos를 한 번만 계산
    theta = math.radians(start_pos_angle)   # 시작 각도를 각도에서 라디안으로 변환
    cos_t, sin_t = math.cos(theta), math.sin(theta) # 시작각의 cos와 sin을 미리 계산 : 번째 점의 초기 방향 벡터를 만들 때 사용.
    cos_d, sin_d = math.cos(delta), math.sin(delta) # 증분각의 cos와 sin을 미리 계산 : 재계산을 안함으로서 속도 최적화

    ### 시작 벡터 r*[cosθ, sinθ]
    vx, vz = radius * cos_t, radius * sin_t    # 중심으로부터 start_pos_angle만큼 떨어진 첫 번째 점의 상대좌표.

    for _ in range(num_nodes):                 # 지정한 노드 개수만큼 반복 (각도마다 한 점 생성).
        # 현재 점 기록
        waypoints.append(x + vx, z + vz, x, z)       # 현재 중심 (x, z)에 벡터 (vx, vz)를 더해 실제 좌표로 변환하고 리스트에 추가.
        # 다음 점 = 회전행렬 * 현재 벡터
        # [vx', vz'] = [vx*cosΔ - vz*sinΔ, vx*sinΔ + vz*cosΔ]
        nvx = vx * cos_d - vz * sin_d          # 회전 행렬을 이용해 벡터를 Δθ만큼 회전
        nvz = vx * sin_d + vz * cos_d
        vx, vz = nvx, nvz                      # 회전 후 벡터를 다음 루프의 기준으로 갱신.

    waypoints.append(x + vx, z + vz, x, z)           # 원의 시작점으로 다시 돌아오는 마지막 점 추가 : 폐곡선 완성을 위해.



# generate_circle_nodes(150, 150, num_nodes = 12, radius = 100, start_pos_angle = 270, reverse=True) 
# # x, z 좌표, 노드 갯수(짝수로 입력할것!), 반지름 넓이, 타겟과 시작 노드 사이의 각도 : 6시 시작 시, 270으로, 반시계방향 여부(bool)


# print(waypoints.to_list())  # 웨이포인트에 generate_circle_nodes가 만든 좌표들이 정상적으로 주입되었는지 확인용
def obstacle_auto_planning(obstacles):
    """
    점 4개를 받아서 조건에 따라 group3에 순서대로 저장하고,
    순서대로 waypoints(연결 리스트)에 추가한다.
    Args:
        obstacles: 점 리스트 [{'x_min': ..., 'x_max': ..., 'z_min': ..., 'z_max': ...}, ...]
    Returns:
        group3: [(x, z), ...] 형태의 리스트
    """
    # 중심좌표 유효성 검사
    for i, obstacle in enumerate(obstacles):
        center_x = (obstacle['x_min'] + obstacle['x_max']) / 2
        center_z = (obstacle['z_min'] + obstacle['z_max']) / 2
        if center_x < 55 or center_x > 245 or center_z < 55 or center_z > 245:
            print(f"!!!!!!!!!!!!!!!!!!!!!!!!!에러: {i+1}번 장애물의 중심좌표(center_x={center_x:.2f}, center_z={center_z:.2f})가 허용 범위를 벗어났습니다.!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
            print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!장애물 좌표는 55 이상 245 이하이어야 합니다. order 분류를 중단합니다.!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
            return []
        
    if len(obstacles) != 4:
        print(f"점 개수가 4개가 아닙니다. 현재: {len(obstacles)}개")
        return []
    
    # 중심좌표 기준으로 분류
    order = [None, None, None, None]
    rest = []
    for obstacle in obstacles:
        center_x = (obstacle['x_min'] + obstacle['x_max']) / 2
        center_z = (obstacle['z_min'] + obstacle['z_max']) / 2

        if center_x < 150 and center_z < 150:
            order[0] = obstacle
        elif center_x < 150 and center_z > 150:
            order[1] = obstacle
        elif center_x > 150 and center_z > 150:
            order[2] = obstacle
        else:
            rest.append(obstacle)

    # 네번째 순서: 남은 점
    if rest:
        order[3] = rest[0]

    # group3에 중심좌표 저장
    group3 = []
    for idx, obstacle in enumerate(order):
        if obstacle is not None:
            center_x = (obstacle['x_min'] + obstacle['x_max']) / 2
            center_z = (obstacle['z_min'] + obstacle['z_max']) / 2
            group3.append((center_x, center_z))
            print(f"{idx+1}번 순서: center_x={center_x:.2f}, center_z={center_z:.2f}")
        else:
            print(f"{idx+1}번 순서: 해당 조건에 맞는 점이 없습니다.")

    # waypoints에 추가
    for x, z in group3:
        waypoints.append(x, z, x, z)

    # 저장된 좌표쌍 출력
    # print("\nWaypoints에 저장된 좌표쌍:")
    # for i, wp in enumerate(waypoints.to_list(), 1):
    #     print(f"  {i}번: x={wp['x']:.2f}, z={wp['z']:.2f}, target_x={wp['target_x']:.2f}, target_z={wp['target_z']:.2f}")

def visualize_waypoints():
    # waypoints 시각화 함수
    wp_list = waypoints.to_list()
    if not wp_list:
        print("시각화할 웨이포인트가 없습니다.")
        return

    x_list = [wp['x'] for wp in wp_list]
    z_list = [wp['z'] for wp in wp_list]

    plt.figure(figsize=(8, 8))
    plt.plot(x_list, z_list, marker='o', linestyle='-', color='b', label='Waypoints Path')
    plt.scatter(x_list, z_list, c='red', s=80, label='Waypoints')
    for i, (x, z) in enumerate(zip(x_list, z_list)):
        plt.text(x, z, str(i+1), fontsize=10, ha='right', va='bottom')
    plt.xlabel('X')
    plt.ylabel('Z')
    plt.title('Waypoints Visualization')
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.axis('equal')
    plt.xlim(0, 300)
    plt.ylim(0, 300)
    plt.tight_layout()
    # 파일로 저장
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"source/research/body_control/path_tracking/basic_path_tracking/waypoints_{timestamp}.png"
    plt.savefig(filename, dpi=200, bbox_inches='tight')
    # print(f"Waypoints 시각화 이미지를 저장했습니다: {filename}")
    # plt.show()  # 필요시 주석 해제

def obstacle_auto_planning_and_generate_circle_nodes(obstacles):
    obstacle_auto_planning(obstacles)

    if len(obstacles) == 4:
        sorted_list = []

        for waypoint in waypoints.to_list():
            sorted_list.append((waypoint['x'], waypoint['z']))
            waypoints.pop()
        print("sorted_list: ", sorted_list)

        for i in sorted_list:
            generate_circle_nodes(i[0], i[1], num_nodes=12, radius=50, start_pos_angle=330, reverse=True)

        print("생성된 원형 경로: ", waypoints.to_list())

        visualize_waypoints()
# --------------------------------------------------------------------

def path_finding(): # 경로 탐색 함수
    # not yet
    path = waypoints
    return path

def path_tracking(player_x, player_z, player_body_x, player_speed): # 경로 추적 함수
    print("path_tracking")
    # 커맨드 초기화
    WS_command, WS_weight, AD_command, AD_weight = "", 0.0, "", 0.0
    global right_flag, left_flag
    right_flag, left_flag = False, False
    # path: 여러 개의 웨이포인트로 구성된 경로
    # 초기: 단순 웨이포인트 추적 로직
    # 중장기: 코너링에 대한 Catmull-Rom Spline 보간을 통해 부드러운 경로 생성 및 추적으로 할지

    # (도착 판단 및 웨이포인트 교체)1. 현재 웨이포인트 선택 및 도달 여부 확인
    while True:
        current_waypoint = waypoints.peek()
        # print("\n\n\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!peek!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n\n\n")
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

    
    print("Target Angle:", target_angle)

    # (회전)2. 현재 탱크의 수직각, 수평각을 확인하여 웨이포인트 방향으로 회전 명령 생성
    # - 전속력(weight = 1.0) 회전 수행
    # - 만약, 탱크의 수평각이 목표 수평각보다 5도 이내로 들어오면, 회전 명령 중지
    angle_diff = (target_angle - player_body_x + 540) % 360 - 180
    angle_diff = abs(angle_diff)

    print("Angle Diff:", angle_diff)
    print("Player Body X:", player_body_x)
    if angle_diff > 20:
        if (player_body_x - target_angle + 360) % 360 > 180:
            AD_command, AD_weight = "D", 1.0
            right_flag = True # 차체 우측 회전 시 Trueㅍ
            left_flag = False
            print("Rotate D 1.0")
        else:
            AD_command, AD_weight = "A", 1.0
            right_flag = False
            left_flag = True # 차체 좌측 회전 시 True
            print("Rotate A 1.0")

    # (회전) 3. 회전 명령 중지 후, 만약, 탱크의 수평각이 목표 수평각보다 1도 이상 크거나, 작으면, 반대로 역 조정 명령 생성
    elif angle_diff > 0.8:
        AD_command, AD_weight = "", 0.0 # 명령 초기화
        if player_body_x - target_angle > 0.5:
            print("Rotate A 0.05")
            AD_command, AD_weight = "A", 0.05
        elif player_body_x - target_angle < -0.5:
            print("Rotate D 0.05")
            AD_command, AD_weight = "D", 0.05
    # (회전) 4. 만약, 탱크의 회전각이 웨이포인트 방향과 일치하면, 저속 전진 명령 생성
    elif angle_diff <= 0.8:
        left_flag = False
        right_flag = False # 차체 전진 시, 회전 신호 off
        print("W <= 0.8")
        WS_command, WS_weight = "W", 0.3
        # print("Move W 0.3")

    return WS_command, WS_weight, AD_command, AD_weight

def stabilizer(player_x, player_y, player_z, player_turret_x, player_turret_y, enemy_x, enemy_y, enemy_z):
    QE_command, QE_weight, RF_command, RF_weight = "", 0.0, "", 0.0

    if left_flag == False and right_flag == False: # 회전하지 않으면, 일반 스테빌라이저 실행
        print("!!!General Stabilizer!!!")
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
    if right_flag == True: # 차체 우측 회전 일 때, 터렛 좌측 역 방향 회전
        print("!!!Stabilizer RIGHT!!!")
        QE_command, QE_weight = "Q", 0.999
    if left_flag == True: # 차체 좌측 회전 일 때, 터렛 우측 역 방향 회전
        print("!!!Stabilizer LEFT!!!")
        QE_command, QE_weight = "E", 0.999

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
        temp = waypoints.peek() # 옵스타클 탐지용 
        if temp is not None:
            target_x = getattr(temp, 'target_x', temp.x)
            target_z = getattr(temp, 'target_z', temp.z)
            QE_command, QE_weight, RF_command, RF_weight = stabilizer(
                player_x, player_y, player_z, player_turret_x, player_turret_y, target_x, enemy_y, target_z
            )
        else:
            # 웨이포인트가 없을 때의 처리 (예: 명령 초기화)
            QE_command, QE_weight, RF_command, RF_weight = "", 0.0, "", 0.0
        # QE_command, QE_weight, RF_command, RF_weight = stabilizer(player_x, player_y, player_z, player_turret_x, player_turret_y, enemy_x, enemy_y, enemy_z) # 스테빌 라이저로 마지막으로 포착된 적 위치에 조준 안정화
        # QE_command, QE_weight, RF_command, RF_weight = stabilizer(player_x, player_y, player_z, player_turret_x, player_turret_y, temp.target_x, enemy_y, temp.target_z) # 옵스타클 탐지용

    elif enemy_detection == True and enemy_in_fov == True: # 적이 탐지되고, 시야에 있는 경우
        QE_command, QE_weight, RF_command, RF_weight, fire_command = fire_calculation() # 사격 계산 수행하여 조준 및 사격 명령

    return QE_command, QE_weight, RF_command, RF_weight, fire_command

def body_control(player_x, player_z, player_body_x, player_speed): # 차체 제어 함수
    # 초기화
    WS_command, WS_weight, AD_command, AD_weight = 0.0, 0.0, 0.0, 0.0
    print("body_control")
    # path = path_finding() # 경로 탐색 함수

    WS_command, WS_weight, AD_command, AD_weight = path_tracking(player_x, player_z, player_body_x, player_speed)
    
    return WS_command, WS_weight, AD_command, AD_weight

# --------------------------------------------------------------------

app = Flask(__name__) # Flask 앱 생성
# --------------------------------------------------------------------

@app.route('/info', methods=['POST'])
def info():
    global global_QE_command, global_QE_weight, global_RF_command, global_RF_weight # turret
    global global_WS_command, global_WS_weight, global_AD_command, global_AD_weight # body
    global global_fire_command # fire
    global enemy_detection, enemy_in_fov # detect API

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

    # Body Control
    global_WS_command, global_WS_weight, global_AD_command, global_AD_weight = body_control(player_x, player_z, player_body_x, player_speed)

    # Turret Control
    global_QE_command, global_QE_weight, global_RF_command, global_RF_weight, global_fire_command = turret_control(enemy_detection, enemy_in_fov, player_x, player_y, player_z, player_turret_x, player_turret_y, enemy_x, enemy_y, enemy_z)

    return jsonify({"status": "success", "control": ""})

# --------------------------------------------------------------------

@app.route('/get_action', methods=['POST'])
def get_action():
    global global_QE_command, global_QE_weight, global_RF_command, global_RF_weight # turret
    global global_WS_command, global_WS_weight, global_AD_command, global_AD_weight # body
    global global_fire_command # fire

    # 기존에 계산된 명령어와 가중치에 따라 행동 결정
    action = {
        "moveWS":  {"command": global_WS_command, "weight": global_WS_weight},
        "moveAD":  {"command": global_AD_command, "weight": global_AD_weight},
        "turretQE": {"command": global_QE_command, "weight": global_QE_weight},
        "turretRF": {"command": global_RF_command, "weight": global_RF_weight},
        "fire":     global_fire_command
    }
    
    return jsonify(action)

# --------------------------------------------------------------------

@app.route('/update_obstacle', methods=['POST'])
def update_obstacle():
    print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!UPDATE OBSTACLE CALLED!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    data = request.get_json(force=True)

    # exception handling
    if not data:
        return jsonify({"error": "No JSON received"}), 400

    # print("Received obstacle data:", data["obstacles"])

    obstacle_auto_planning_and_generate_circle_nodes(data["obstacles"])

    return jsonify({"status": "OK"})

# --------------------------------------------------------------------

#Endpoint called when the episode starts
@app.route('/init', methods=['GET'])
def init():
    config = {
        "startMode": "start",  # Options: "start" or "pause"
        "blStartX": 150,  #Blue Start Position
        "blStartY": 10,
        "blStartZ": 0,
        "rdStartX": 150, #Red Start Position
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
    # print("Initialization config sent via /init:", config)
    return jsonify(config)

# --------------------------------------------------------------------

@app.route('/start', methods=['GET'])
def start():
    # print("🚀 /start command received")
    return jsonify({"control": ""})

# --------------------------------------------------------------------

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

# --------------------------------------------------------------------
