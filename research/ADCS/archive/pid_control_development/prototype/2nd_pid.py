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

# -------------------------------------------------------------------
# PID Controller for turret stabilizer

# -------------------------------------------------------------------
# PID Controller for turret stabilizer

class PIDController:
    def __init__(self, kp, ki, kd, integrator_limit=None, deriv_filter_tau=0.01):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.integrator = 0.0
        self.prev_error = 0.0
        self.derivative = 0.0
        self.integrator_limit = integrator_limit
        self.deriv_filter_tau = deriv_filter_tau

    def reset(self):
        self.integrator = 0.0
        self.prev_error = 0.0
        self.derivative = 0.0

    def compute(self, setpoint, measured_value, dt):
        # error = setpoint - measured
        error = setpoint - measured_value

        if dt <= 0:
            dt = 0.11  # fallback

        # 적분항
        self.integrator += error * dt
        if self.integrator_limit is not None:
            self.integrator = max(-self.integrator_limit,
                                  min(self.integrator, self.integrator_limit))

        # 미분항 (저역통과 필터)
        raw_deriv = (error - self.prev_error) / dt
        alpha = dt / (self.deriv_filter_tau + dt)
        self.derivative = (1 - alpha) * self.derivative + alpha * raw_deriv

        # PID 합산
        u = self.kp * error + self.ki * self.integrator + self.kd * self.derivative

        self.prev_error = error
        return u

def normalize_angle_deg(angle):
    """각도를 -180 ~ 180도로 정규화"""
    return (angle + 180.0) % 360.0 - 180.0


def map_yaw_control_to_QE(u, deadband=0.2, max_u=16.0):
    """
    yaw PID 출력(u)을 Q/E 명령과 weight(0~1)로 변환
    u > 0 : 오른쪽 회전(E)
    u < 0 : 왼쪽 회전(Q)
    """
    if abs(u) < deadband:
        return "", 0.0

    u_clamped = max(-max_u, min(max_u, u))
    weight = abs(u_clamped) / max_u

    if u_clamped > 0:
        return "E", weight
    else:
        return "Q", weight


def map_pitch_control_to_RF(u, deadband=0.3, max_u=20.0):
    """
    pitch PID 출력(u)을 R/F 명령과 weight로 변환
    u > 0 : 위로(R)
    u < 0 : 아래로(F)
    """
    if abs(u) < deadband:
        return "", 0.0

    u_clamped = max(-max_u, min(max_u, u))
    weight = abs(u_clamped) / max_u

    if u_clamped > 0:
        return "R", weight
    else:
        return "F", weight


# 포탑 yaw/pitch용 PID 인스턴스 (게인은 추후 튜닝)
turret_yaw_pid = PIDController(
    kp=0.70,        # 0.78 → 0.70 : 반응 조금 줄여서 오버슈트 줄이기
    ki=0.015,       # 0   → 0.015 : 아주 약한 I로 중심에서 남는 steady-state error를 없앰
    kd=0.28,        # 0.27 → 0.28 : 살짝 더 강한 D로 진동/overshoot 감쇠
    integrator_limit=10.0,  # 20 → 10 : I가 과하게 쌓이지 않도록 제한
    deriv_filter_tau=0.08   # 0.09 → 0.08 : D를 조금 더 빠르게 반응시키되 너무 예민하진 않게
)

turret_pitch_pid = PIDController(
    kp=0.55,
    ki=0.0,          # pitch는 PD (I=0)
    kd=0.12,
    integrator_limit=30.0,
    deriv_filter_tau=0.04
)

# /info 루프용 이전 시간
prev_time = None

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
            generate_circle_nodes(i[0], i[1], num_nodes=8, radius=60, start_pos_angle=330, reverse=True)

        print("생성된 원형 경로: ", waypoints.to_list())

        visualize_waypoints()
# --------------------------------------------------------------------

def path_finding(): # 경로 탐색 함수
    # not yet
    path = waypoints
    return path

def path_tracking(player_x, player_z, player_body_x, player_speed):
    print("path_tracking")
    # 커맨드 초기화
    WS_command, WS_weight, AD_command, AD_weight = "", 0.0, "", 0.0

    # 1. 현재 웨이포인트 선택
    current_waypoint = waypoints.peek()
    if current_waypoint is None:
        # 웨이포인트가 없으면 정지
        WS_command, WS_weight = "STOP", 1.0
        return WS_command, WS_weight, AD_command, AD_weight

    while True:
        distance = math.sqrt((current_waypoint.x - player_x)**2 +
                             (current_waypoint.z - player_z)**2)
        print("Distance to Waypoint:", distance)

        # 도착 판단: 1.0m 이내면 도달한 것으로 간주하고 다음 웨이포인트로
        if distance <= 1.0:
            print("\n\n\n=== REACHED WAYPOINT ===\n\n\n")
            waypoints.pop()
            current_waypoint = waypoints.peek()
            if current_waypoint is None:
                WS_command, WS_weight = "STOP", 1.0
                return WS_command, WS_weight, AD_command, AD_weight
            # 다음 웨이포인트 기준으로 다시 distance 계산
            continue
        break

    print("현재 향하는 웨이포인트:", current_waypoint.x, current_waypoint.z)

    # 목표 각도 계산
    dx = current_waypoint.x - player_x
    dz = current_waypoint.z - player_z
    target_angle = math.degrees(math.atan2(dx, dz)) % 360
    print("Target Angle:", target_angle)

    # 현재 차체 각도와의 차이
    angle_diff = (target_angle - player_body_x + 540) % 360 - 180
    abs_angle_diff = abs(angle_diff)

    print("Angle Diff:", abs_angle_diff)
    print("Player Body X:", player_body_x)

    # 1) 큰 각도 차이: 빠른 회전
    if abs_angle_diff > 20:
        if angle_diff > 0:
            AD_command, AD_weight = "D", 1.0
            print("Rotate D 1.0")
        else:
            AD_command, AD_weight = "A", 1.0
            print("Rotate A 1.0")

    # 2) 중간 각도 차이: 미세 회전
    elif abs_angle_diff > 0.8:
        if angle_diff > 0.5:
            AD_command, AD_weight = "D", 0.05
            print("Rotate D 0.05")
        elif angle_diff < -0.5:
            AD_command, AD_weight = "A", 0.05
            print("Rotate A 0.05")

    # 3) 거의 정렬된 경우: 전진
    else:
        print("W <= 0.8")
        WS_command, WS_weight = "W", 0.3

    return WS_command, WS_weight, AD_command, AD_weight

def stabilizer(player_x, player_y, player_z,
               player_turret_x, player_turret_y,
               target_x, target_y, target_z,
               dt):
    """
    PID 기반 포탑 스테빌라이저
    - 좌우(Q/E): turret_yaw_pid
    - 상하(R/F): turret_pitch_pid
    항상 PID를 사용해서 target을 조준하도록 함.
    (차체 회전 플래그에 의해 override 하지 않음)
    """
    QE_command, QE_weight, RF_command, RF_weight = "", 0.0, "", 0.0

    # 상대 위치
    dx = target_x - player_x
    dz = target_z - player_z
    dy = target_y - player_y

    # XZ 평면 거리
    distance_xz = math.hypot(dx, dz)

    # 목표 pitch (상하 각도)
    target_pitch = math.degrees(math.atan2(dy, distance_xz))

    # 목표 yaw (좌우 각도)
    yaw_rad = math.atan2(dx, dz)
    target_yaw = math.degrees(yaw_rad)
    if target_yaw < 0:
        target_yaw += 360.0

    # yaw 오차 (-180 ~ 180도로 정규화)
    yaw_angle_diff = normalize_angle_deg(target_yaw - player_turret_x)
    # pitch 오차
    pitch_angle_diff = target_pitch - player_turret_y

    # PID 사용 (setpoint 0, measured -diff → error = diff)
    yaw_control = turret_yaw_pid.compute(
        setpoint=0.0,
        measured_value=-yaw_angle_diff,
        dt=dt
    )
    pitch_control = turret_pitch_pid.compute(
        setpoint=0.0,
        measured_value=-pitch_angle_diff,
        dt=dt
    )

    # PID 출력 → 명령 매핑
    QE_command, QE_weight = map_yaw_control_to_QE(yaw_control)
    RF_command, RF_weight = map_pitch_control_to_RF(pitch_control)

    return QE_command, QE_weight, RF_command, RF_weight, yaw_angle_diff, pitch_angle_diff, distance_xz

def fire_calculation(): # 사격 계산 함수
    QE_command, QE_weight, RF_command, RF_weight, fire_command = 0.0, 0.0, 0.0, 0.0, False
    return QE_command, QE_weight, RF_command, RF_weight, fire_command

def turret_control(enemy_detection, enemy_in_fov,
                   player_x, player_y, player_z,
                   player_turret_x, player_turret_y,
                   enemy_x, enemy_y, enemy_z,
                   dt):
    """
    포탑 제어 함수 (PID 스테빌라이저 + 발사 판단)
    - enemy_detection / enemy_in_fov 를 외부에서 그대로 받아서 사용
    - in_fov 여부와 웨이포인트 유무에 따라 조준 타겟을 선택
    """
    print("turret_control")

    QE_command, QE_weight = "", 0.0
    RF_command, RF_weight = "", 0.0
    fire_command = False

    # 1) 조준할 타겟 선택
    temp_wp = waypoints.peek()
    target_x, target_y, target_z = None, None, None

    if enemy_detection:
        if enemy_in_fov:
            # 적이 시야 안에 있을 때: 적을 직접 조준
            target_x, target_y, target_z = enemy_x, enemy_y, enemy_z
        else:
            # 적은 탐지됐지만 시야 밖: 웨이포인트(장애물) 기준 조준 or 마지막 적 위치
            if temp_wp is not None:
                target_x = getattr(temp_wp, 'target_x', temp_wp.x)
                target_z = getattr(temp_wp, 'target_z', temp_wp.z)
                target_y = enemy_y  # 높이는 적 높이 수준으로 가정
            else:
                # 웨이포인트도 없다면, 그냥 적의 현재/마지막 좌표를 기준으로 안정화
                target_x, target_y, target_z = enemy_x, enemy_y, enemy_z
    else:
        # 적 자체를 탐지 못하는 경우: 장애물 중심을 바라보는 용도
        if temp_wp is not None:
            target_x = getattr(temp_wp, 'target_x', temp_wp.x)
            target_z = getattr(temp_wp, 'target_z', temp_wp.z)
            target_y = player_y  # 내 위치 높이 기준
        else:
            # 조준할 대상이 없으면 포탑 제어 안 함
            return QE_command, QE_weight, RF_command, RF_weight, fire_command

    # 2) 선택된 타겟을 향해 PID 스테빌라이저 동작
    QE_command, QE_weight, RF_command, RF_weight, \
        yaw_err, pitch_err, dist_xz = stabilizer(
            player_x, player_y, player_z,
            player_turret_x, player_turret_y,
            target_x, target_y, target_z,
            dt
        )

    # 3) 발사 판단: 적이 시야에 있을 때만 발사 후보 판단
    if enemy_detection and enemy_in_fov:
        fire_command = fire_calculation(yaw_err, pitch_err, dist_xz)
    else:
        fire_command = False

    # 디버그 로그 예시
    print(f"[Turret] yaw_err={yaw_err:.2f}, pitch_err={pitch_err:.2f}, dist={dist_xz:.1f}, "
          f"QE={QE_command}({QE_weight:.2f}), RF={RF_command}({RF_weight:.2f}), fire={fire_command}")

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
    global global_QE_command, global_QE_weight, global_RF_command, global_RF_weight
    global global_WS_command, global_WS_weight, global_AD_command, global_AD_weight
    global global_fire_command
    global enemy_detection, enemy_in_fov
    global prev_time

    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "No JSON received"}), 400

    time_val = data["time"]
    distance = data["distance"]

    # dt 계산 (시뮬레이터 시간 기준)
    dt = 0.11  # fallback 기본값
    if prev_time is not None:
        dt_candidate = time_val - prev_time
        if dt_candidate > 0:
            dt = dt_candidate
    prev_time = time_val

    # 플레이어 정보
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

    # 적 정보
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

    # detect 플래그를 외부에서 받는다고 가정 (없으면 기본값 유지)
    enemy_detection = data.get("enemyDetection", enemy_detection)
    enemy_in_fov = data.get("enemyInFov", enemy_in_fov)

    # Body Control
    global_WS_command, global_WS_weight, \
        global_AD_command, global_AD_weight = body_control(
            player_x, player_z, player_body_x, player_speed
        )

    # Turret Control (PID 기반 스테빌라이저 + 발사 판단)
    global_QE_command, global_QE_weight, \
        global_RF_command, global_RF_weight, \
        global_fire_command = turret_control(
            enemy_detection, enemy_in_fov,
            player_x, player_y, player_z,
            player_turret_x, player_turret_y,
            enemy_x, enemy_y, enemy_z,
            dt
        )

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
        "rdStartX": 0, #Red Start Position
        "rdStartY": 10,
        "rdStartZ": 0,
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