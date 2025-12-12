from flask import Flask, request, jsonify
import math
import heapq
import time
from typing import List, Tuple, Set
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
starting_point = [10,10,10]

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

    def clear(self):
        # Utility to clear the list
        self.head = None
        self.tail = None
        self._len = 0

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
        error =  measured_value - setpoint

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


def map_yaw_control_to_QE(u, deadband=0.05, max_u=18.0):
    """
    yaw PID 출력(u)을 Q/E 명령과 weight(0~1)로 변환
    - deadband를 약간 키워서 아주 작은 진동은 무시
    - weight는 비선형(지수) 매핑으로:
      멀 때는 빠르게, 목표 근처에서는 부드럽게 감속
    """
    if abs(u) < deadband:
        return "", 0.0

    u_clamped = max(-max_u, min(max_u, u))

    norm = abs(u_clamped) / max_u
    weight = norm ** 0.8

    if u_clamped > 0:
        return "E", weight
    else:
        return "Q", weight

def map_pitch_control_to_RF(u, deadband=0.3, max_u=20.0):
    if abs(u) < deadband:
        return "", 0.0

    u_clamped = max(-max_u, min(max_u, u))
    weight = abs(u_clamped) / max_u

    if u_clamped > 0:
        return "R", weight
    else:
        return "F", weight


# ✅ ✅ ✅ 추가됨: WS PID Controller
ws_pid = PIDController(
    kp=0.35,      # forward speed response
    ki=0.01,
    kd=0.02,
    integrator_limit=5.0,
    deriv_filter_tau=0.1
)

# ✅ WS PID 출력 → W weight로 맵핑
def map_ws_control(u, deadband=0.05, max_u=10.0):
    if abs(u) < deadband:
        return "", 0.0

    u_clamped = max(0.0, min(max_u, u))  # forward only
    norm = u_clamped / max_u
    weight = norm ** 0.7                 # smoother accel

    return "W", weight


# 포탑 PID instances 그대로 유지
turret_yaw_pid = PIDController(
    kp=0.55,
    ki=0.01,
    kd=0.08,
    integrator_limit=3.0,
    deriv_filter_tau=0.10
)

turret_pitch_pid = PIDController(
    kp=0.55,
    ki=0.0,
    kd=0.08,
    integrator_limit=30.0,
    deriv_filter_tau=0.04
)

prev_time = None
waypoints = WaypointList()

# ------------------ A* Path Planner (integrated) -------------------
GRID_W, GRID_H = 300, 300
ALLOW_DIAGONAL = True
OBST_SIZE = 20
OBST_HALF = OBST_SIZE // 2
CLEARANCE = 3
START_GRID = (starting_point[0], starting_point[2])
GOAL_GRID = (280, 280)

def in_bounds(x, y):
    return 0 <= x < GRID_W and 0 <= y < GRID_H

def neighbors(x, y):
    steps = [(-1,0),(1,0),(0,-1),(0,1)]
    if ALLOW_DIAGONAL:
        steps += [(-1,-1),(-1,1),(1,-1),(1,1)]
    for dx, dy in steps:
        nx, ny = x+dx, y+dy
        if in_bounds(nx, ny):
            yield nx, ny
def heuristic(a, b):
    (x1,y1), (x2,y2) = a, b
    dx, dy = abs(x1-x2), abs(y1-y2)
    if ALLOW_DIAGONAL:
        D, D2 = 1.0, math.sqrt(2.0)
        return D*(dx+dy) + (D2-2*D)*min(dx,dy)   # 옥타일 휴리스틱
    else:
        return dx + dy

def stamp_square(blocked: Set[Tuple[int,int]], cx: int, cy: int, half: int):
    x0, x1 = cx - half, cx + half - 1
    y0, y1 = cy - half, cy + half - 1
    for x in range(x0, x1+1):
        for y in range(y0, y1+1):
            if in_bounds(x, y):
                blocked.add((x, y))

# ------------------ A* (REPLACED) ------------------
def astar(start, goal, blocked: Set[Tuple[int,int]]) -> List[Tuple[int,int]]:
    if start == goal:
        return [start]

    if start in blocked or goal in blocked:
        return []

    D2 = math.sqrt(2.0)
    g = {start: 0.0}
    f = {start: heuristic(start, goal)}
    came = {}
    pq = [(f[start], start)]
    seen = set()

    while pq:
        _, cur = heapq.heappop(pq)
        if cur in seen:
            continue
        seen.add(cur)

        if cur == goal:
            path = [cur]
            while cur in came:
                cur = came[cur]
                path.append(cur)
            path.reverse()
            return path

        cx, cy = cur
        for nx, ny in neighbors(cx, cy):
            if (nx, ny) in blocked:
                continue
            step = D2 if (nx != cx and ny != cy) else 1.0
            ng = g[cur] + step
            if ng < g.get((nx, ny), 1e18):
                came[(nx, ny)] = cur
                g[(nx, ny)] = ng
                f[(nx, ny)] = ng + heuristic((nx, ny), goal)
                heapq.heappush(pq, (f[(nx, ny)], (nx, ny)))
    return []
# ------------------ END REPLACED A* ------------------

def bresenham_line(x0, y0, x1, y1):
    dx = abs(x1 - x0); sx = 1 if x0 < x1 else -1
    dy = -abs(y1 - y0); sy = 1 if y0 < y1 else -1
    err = dx + dy
    x, y = x0, y0
    while True:
        yield (x, y)
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy; x += sx
        if e2 <= dx:
            err += dx; y += sy

def line_blocked(p0, p1, blocked):
    for c in bresenham_line(p0[0], p0[1], p1[0], p1[1]):
        if c in blocked and c not in (p0, p1):
            return True
    return False

def simplify_path_los(path_points, blocked):
    if not path_points:
        return []
    simp = [path_points[0]]
    i = 0
    while i < len(path_points) - 1:
        j = i + 1
        while j + 1 < len(path_points) and not line_blocked(path_points[i], path_points[j + 1], blocked):
            j += 1
        simp.append(path_points[j])
        i = j
    return simp

def fill_waypoints_from_path(path_points: List[Tuple[int,int]]):
    waypoints.clear()
    for p in path_points:
        waypoints.append(float(p[0]), float(p[1]), float(p[0]), float(p[1]))

# ----------------------------- Circle Nodes ---------------------------------

def generate_circle_nodes(x, z, num_nodes, radius, start_pos_angle, reverse):
    if reverse == True:
        delta = 2 * math.pi / num_nodes
    else:
        delta = -2 * math.pi / num_nodes

    theta = math.radians(start_pos_angle)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    cos_d, sin_d = math.cos(delta), math.sin(delta)

    vx, vz = radius * cos_t, radius * sin_t

    for _ in range(num_nodes):
        waypoints.append(x + vx, z + vz, x, z)
        nvx = vx * cos_d - vz * sin_d
        nvz = vx * sin_d + vz * cos_d
        vx, vz = nvx, nvz

    waypoints.append(x + vx, z + vz, x, z)

# -----------------------------------------------------------------------------

def obstacle_auto_planning(obstacles):
    for i, obstacle in enumerate(obstacles):
        center_x = (obstacle['x_min'] + obstacle['x_max']) / 2
        center_z = (obstacle['z_min'] + obstacle['z_max']) / 2
        if center_x < 55 or center_x > 245 or center_z < 55 or center_z > 245:
            print(f"에러: {i+1}번 장애물 중심좌표(center_x={center_x:.2f}, center_z={center_z:.2f}) 범위 초과")
            return []

    if len(obstacles) != 4:
        print(f"점 개수가 4개가 아닙니다. 현재: {len(obstacles)}개")
        return []

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

    if rest:
        order[3] = rest[0]

    group3 = []
    for idx, obstacle in enumerate(order):
        if obstacle is not None:
            center_x = (obstacle['x_min'] + obstacle['x_max']) / 2
            center_z = (obstacle['z_min'] + obstacle['z_max']) / 2
            group3.append((center_x, center_z))
            print(f"{idx+1}번 순서: {center_x:.2f}, {center_z:.2f}")

    for x, z in group3:
        waypoints.append(x, z, x, z)

# -----------------------------------------------------------------------------

def visualize_waypoints():
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

    import datetime
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"source/research/body_control/path_tracking/basic_path_tracking/waypoints_{timestamp}.png"
    plt.savefig(filename, dpi=200, bbox_inches='tight')

# -----------------------------------------------------------------------------

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

    centers = []
    for obs in obstacles:
        cx = int(round((obs['x_min'] + obs['x_max']) / 2.0))
        cz = int(round((obs['z_min'] + obs['z_max']) / 2.0))
        centers.append((cx, cz))

    blocked_inflated: Set[Tuple[int, int]] = set()
    infl_half = OBST_HALF + CLEARANCE
    for (cx, cz) in centers:
        stamp_square(blocked_inflated, cx, cz, infl_half)

    path = astar(START_GRID, GOAL_GRID, blocked_inflated)
    if path:
        path2 = simplify_path_los(path, blocked_inflated)
        fill_waypoints_from_path(path2)
        print("A* 기반으로 생성된 waypoints 수:", len(path2))
    else:
        print("A* 경로를 찾지 못했습니다 (update_obstacle).")
def path_finding(): # 경로 탐색 함수
    path = waypoints
    return path

# ======================================
# ✅ WS PID CONTROLLER + mapping
# ======================================

# --- 새 전진 PID 컨트롤러 (스무스 가감속용) ---
ws_pid = PIDController(
    kp=0.35,
    ki=0.01,
    kd=0.02,
    integrator_limit=5.0,
    deriv_filter_tau=0.1
)

# --- PID 출력 → W / S + weight 매핑 ---
def map_ws_control(u, deadband=0.05, max_u=10.0):
    """
    PID 출력 u를 W/S 명령과 weight(0~1)로 변환
    - u > 0 → 전진(W)
    - u < 0 → 후진(S)
    - 거의 0이면 정지(0 weight)
    """
    if abs(u) < deadband:
        return "", 0.0

    u_clamped = max(-max_u, min(max_u, u))

    weight = abs(u_clamped) / max_u
    weight = weight ** 0.65  # 부드러운 상승

    if u_clamped > 0:
        return "W", weight
    else:
        return "S", weight

# ======================================
# ✅ 개선된 path_tracking (WS PID 통합)
# ======================================
def path_tracking(player_x, player_z, player_body_x):
    print("path_tracking")

    WS_command, WS_weight, AD_command, AD_weight = "", 0.0, "", 0.0

    current_waypoint = waypoints.peek()
    if current_waypoint is None:
        WS_command, WS_weight = "STOP", 1.0
        return WS_command, WS_weight, AD_command, AD_weight

    # --- dt 계산 (fallback = 0.03) ---
    global prev_time
    dt = 0.03
    if prev_time is not None:
        dt_candidate = time.time() - prev_time
        if dt_candidate > 0:
            dt = dt_candidate
    prev_time = time.time()

    # =============== WAYPOINT 도달 체크 ===============
    while True:
        distance = math.sqrt((current_waypoint.x - player_x)**2 +
                             (current_waypoint.z - player_z)**2)

        print("Distance to Waypoint:", distance)

        if distance <= 10:
            print("\n=== REACHED WAYPOINT ===\n")
            waypoints.pop()
            current_waypoint = waypoints.peek()
            if current_waypoint is None:
                WS_command, WS_weight = "STOP", 1.0
                return WS_command, WS_weight, AD_command, AD_weight
            continue
        break

    print("현재 향하는 웨이포인트:", current_waypoint.x, current_waypoint.z)

    # =============== 목표 각도 계산 ===============
    dx = current_waypoint.x - player_x
    dz = current_waypoint.z - player_z
    target_angle = math.degrees(math.atan2(dx, dz)) % 360
    print("Target Angle:", target_angle)

    angle_diff = (target_angle - player_body_x + 540) % 360 - 180
    abs_angle_diff = abs(angle_diff)
    print("Angle Diff:", abs_angle_diff)

    # ===========================
    # AD(조향) 처리 (기존 로직 그대로)
    # ===========================

    if abs_angle_diff > 20:
        if angle_diff > 0:
            AD_command, AD_weight = "D", 1.0
        else:
            AD_command, AD_weight = "A", 1.0

    elif abs_angle_diff > 0.8:
        if angle_diff > 0.5:
            AD_command, AD_weight = "D", 0.05
        elif angle_diff < -0.5:
            AD_command, AD_weight = "A", 0.05

    # ==================================================================
    # ✅ WS PID 제어 — 조향 중에도 "멈추는 것 없이" 전진 속도 스무스하게
    # ==================================================================
    # 여기서 핵심은 distance(웨이포인트까지 거리)를 제어 입력으로 사용
    # setpoint: 0 → 목표는 거리 0 (도달)
    # measured_value: 현재 거리
    # PID 출력값 u가 속도 지령이 됨
    # ==================================================================

    # Compute PID output
    u = ws_pid.compute(
        setpoint=0.0,
        measured_value=distance,
        dt=dt
    )

    # Convert u to WS command + weight
    WS_command, WS_weight = map_ws_control(u)

    print(f"WS PID u = {u:.3f}, mapped → {WS_command}({WS_weight:.3f})")

    return WS_command, WS_weight, AD_command, AD_weight

# --------------------------------------------------------------------

def body_control(player_x, player_z, player_body_x):
    print("body_control")

    WS_command, WS_weight, AD_command, AD_weight = path_tracking(
        player_x, player_z, player_body_x
    )

    return WS_command, WS_weight, AD_command, AD_weight

# --------------------------------------------------------------------

app = Flask(__name__)

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

    # dt 계산
    dt = 0.03
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

    # detect 플래그
    enemy_detection = data.get("enemyDetection", enemy_detection)
    enemy_in_fov = data.get("enemyInFov", enemy_in_fov)

    # Body Control
    global_WS_command, global_WS_weight, \
        global_AD_command, global_AD_weight = body_control(
            player_x, player_z, player_body_x
        )

    # Turret Control
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
    global global_QE_command, global_QE_weight, global_RF_command, global_RF_weight
    global global_WS_command, global_WS_weight, global_AD_command, global_AD_weight
    global global_fire_command

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
    print("UPDATE OBSTACLE CALLED")
    data = request.get_json(force=True)

    if not data:
        return jsonify({"error": "No JSON received"}), 400

    obstacle_auto_planning_and_generate_circle_nodes(data["obstacles"])

    return jsonify({"status": "OK"})

# --------------------------------------------------------------------

@app.route('/init', methods=['GET'])
def init():
    config = {
        "startMode": "start",
        "blStartX": starting_point[0],
        "blStartY": starting_point[1],
        "blStartZ": starting_point[2],
        "rdStartX": 0,
        "rdStartY": 10,
        "rdStartZ": 300,
        "trackingMode": True,
        "detactMode": False,
        "logMode": True,
        "enemyTracking": False,
        "saveSnapshot": False,
        "saveLog": True,
        "saveLidarData": False,
        "lux": 30000
    }
    return jsonify(config)

@app.route('/start', methods=['GET'])
def start():
    return jsonify({"control": ""})

# --------------------------------------------------------------------

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
