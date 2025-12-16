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
        self.head = None
        self.tail = None
        self._len = 0

    def append(self, x, z, target_x, target_z):
        node = WaypointNode(x, z, target_x, target_z)
        if not self.head:
            self.head = self.tail = node
        else:
            self.tail.next = node
            self.tail = node
        self._len += 1
        return node
    
    def peek(self):
        return self.head

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

    def is_empty(self):
        return self.head is None

    def to_list(self):
        out = []
        cur = self.head
        while cur:
            out.append({
                'x': cur.x,
                'z': cur.z,
                'target_x': cur.target_x,
                'target_z': cur.target_z
            })
            cur = cur.next
        return out

    def clear(self):
        self.head = None
        self.tail = None
        self._len = 0

# -------------------------------------------------------------------
# PID Controller (unchanged)
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
        # ✅ reversed error for WS PID compatibility (keeps existing logic stable)
        error = measured_value - setpoint

        if dt <= 0:
            dt = 0.11

        self.integrator += error * dt
        if self.integrator_limit is not None:
            self.integrator = max(-self.integrator_limit,
                                  min(self.integrator, self.integrator_limit))

        raw_deriv = (error - self.prev_error) / dt
        alpha = dt / (self.deriv_filter_tau + dt)
        self.derivative = (1 - alpha) * self.derivative + alpha * raw_deriv

        u = self.kp * error + self.ki * self.integrator + self.kd * self.derivative

        self.prev_error = error
        return u

def normalize_angle_deg(angle):
    return (angle + 180.0) % 360.0 - 180.0
def map_yaw_control_to_QE(u, deadband=0.05, max_u=18.0):
    """
    yaw PID 출력(u)을 Q/E 명령과 weight(0~1)로 변환
    - 작은 떨림 무시, 비선형 매핑으로 근처 감속
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

# /info 루프용 이전 시간
prev_time = None

# Path Planning
waypoints = WaypointList()

# ------------------ A* Path Planner (integrated) -------------------
GRID_W, GRID_H = 300, 300        # 300 x 300 (1셀 = 1 단위)
ALLOW_DIAGONAL = True            # 8방향
OBST_SIZE      = 20              # 장애물 한 변 길이 (정사각형)
OBST_HALF      = OBST_SIZE // 2  # 10
CLEARANCE      = 3               # 장애물과 최소거리 3칸(팽창 반경)
starting_point = starting_point  # 그대로 유지
START_GRID     = (starting_point[0], starting_point[2])
GOAL_GRID      = (280, 280)

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
        return D*(dx+dy) + (D2-2*D)*min(dx,dy)   # 옥타일
    else:
        return dx + dy

def stamp_square(blocked: Set[Tuple[int,int]], cx: int, cy: int, half: int):
    x0, x1 = cx - half, cx + half - 1
    y0, y1 = cy - half, cy + half - 1
    for x in range(x0, x1+1):
        for y in range(y0, y1+1):
            if in_bounds(x, y):
                blocked.add((x, y))

# ------------------ A* (dynamic-sim variant) ------------------
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

# --------------------------------------------------------------------

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

def obstacle_auto_planning(obstacles):
    for i, obstacle in enumerate(obstacles):
        center_x = (obstacle['x_min'] + obstacle['x_max']) / 2
        center_z = (obstacle['z_min'] + obstacle['z_max']) / 2
        if center_x < 55 or center_x > 245 or center_z < 55 or center_z > 245:
            print(f"에러: {i+1}번 장애물 중심({center_x:.2f},{center_z:.2f}) 범위 밖")
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
            print(f"{idx+1}번 순서: center_x={center_x:.2f}, center_z={center_z:.2f}")
        else:
            print(f"{idx+1}번 순서: 없음")

    for x, z in group3:
        waypoints.append(x, z, x, z)

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

# --------------------------------------------------------------------

def path_finding(): # 경로 탐색 함수
    path = waypoints
    return path


# ====== Cross-Coupled Heading/Speed Controller (path_tracking) ======
# 전역(간단 저역통과) 필터 상태
_ws_smooth_prev = 0.0

def _smooth01(x):
    # 0~1 범위 스무스스텝
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)

def path_tracking(player_x, player_z, player_body_x):
    """
    - 각도 오차 → AD weight (연속값) 계산
    - 거리 기반 기본 W 가중치 × (1 - k_rot * AD_weight) 로 크로스 커플링
    - 도달 판정 완화: arrive_radius 내에 들어오면 다음 노드로 넘어감(정확히 찍지 않음)
    - 지나친 노드는 버리고 다음 노드 진행
    """
    global _ws_smooth_prev

    WS_command, WS_weight, AD_command, AD_weight = "", 0.0, "", 0.0
    current_waypoint = waypoints.peek()
    if current_waypoint is None:
        WS_command, WS_weight = "STOP", 1.0
        return WS_command, WS_weight, AD_command, AD_weight

    # --- 반복적으로 도달한 노드 제거 (완화된 반경)
    arrive_radius = 6.0   # 도달 판정 반경(완화)
    while current_waypoint is not None:
        dx0 = current_waypoint.x - player_x
        dz0 = current_waypoint.z - player_z
        dist0 = math.hypot(dx0, dz0)
        if dist0 <= arrive_radius:
            waypoints.pop()
            current_waypoint = waypoints.peek()
            continue
        break

    if current_waypoint is None:
        WS_command, WS_weight = "STOP", 1.0
        return WS_command, WS_weight, AD_command, AD_weight

    # --- 목표 각/거리 계산
    dx = current_waypoint.x - player_x
    dz = current_waypoint.z - player_z
    distance = math.hypot(dx, dz)

    target_angle = math.degrees(math.atan2(dx, dz)) % 360
    angle_diff = (target_angle - player_body_x + 540) % 360 - 180
    abs_angle = abs(angle_diff)

    # --- 회전(AD) weight: 부드러운 연속값 맵핑 (0~90도 구간 중심)
    # 0도 -> 0, 45도 -> ~0.7, 90도 -> 1.0 (클램프)
    ang_norm = min(abs_angle, 90.0) / 90.0
    AD_weight = _smooth01(ang_norm)  # 0~1

    if angle_diff > 0:
        AD_command = "D"
    elif angle_diff < 0:
        AD_command = "A"
    else:
        AD_command = ""
        AD_weight = 0.0

    # --- 전진(W) weight: 거리 기반 기본값 × (1 - k_rot * AD_weight)
    # 거리 맵핑: d<=2 → 0, d>=50 → 1 (스무스)
    d_min, d_max = 2.0, 50.0
    d_norm = (distance - d_min) / (d_max - d_min)
    base_W = _smooth01(d_norm)  # 0~1

    k_rot = 0.85  # 회전이 클수록 전진 감속
    WS_weight_raw = base_W * (1.0 - k_rot * AD_weight)

    # --- 미세 진동 억제(간단 저역통과)
    alpha = 0.35
    WS_weight = alpha * WS_weight_raw + (1 - alpha) * _ws_smooth_prev
    _ws_smooth_prev = WS_weight

    # --- 커맨드/데드밴드
    if WS_weight > 0.03:
        WS_command = "W"
    else:
        WS_command, WS_weight = "", 0.0

    return WS_command, WS_weight, AD_command, AD_weight
def stabilizer(player_x, player_y, player_z,
               player_turret_x, player_turret_y,
               target_x, target_y, target_z,
               body_AD_command, body_AD_weight,
               dt):
    """
    PID 기반 포탑 스테빌라이저
    - 좌우(Q/E): turret_yaw_pid
    - 상하(R/F): turret_pitch_pid
    + 차체 Yaw(A/D) 피드포워드로 안정화 보정
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

    # yaw/pitch 오차
    yaw_angle_diff = normalize_angle_deg(target_yaw - player_turret_x)
    pitch_angle_diff = target_pitch - player_turret_y

    # ===== YAW: PID + Q/E 매핑 =====
    yaw_control = turret_yaw_pid.compute(
        setpoint=0.0,
        measured_value=-yaw_angle_diff,  # error = yaw_diff
        dt=dt
    )
    QE_command, QE_weight = map_yaw_control_to_QE(
        yaw_control,
        deadband=0.05,
        max_u=18.0
    )

    # ===== 차체 회전(A/D)에 대한 피드포워드 보정 =====
    # A(좌)  -> 포탑은 E(우)로 같은 weight
    # D(우)  -> 포탑은 Q(좌)로 같은 weight
    comp_cmd = ""
    comp_weight = 0.0
    if body_AD_command == "A":
        comp_cmd = "E"
        comp_weight = body_AD_weight
    elif body_AD_command == "D":
        comp_cmd = "Q"
        comp_weight = body_AD_weight

    # PID 출력(QE)과 보정(cmd)을 하나의 weight로 합성
    # 1) 먼저 각 방향을 부호가 있는 값으로 바꾼다.  E = +, Q = -
    q_pid = 0.0
    if QE_command == "E":
        q_pid = QE_weight
    elif QE_command == "Q":
        q_pid = -QE_weight

    q_comp = 0.0
    if comp_cmd == "E":
        q_comp = comp_weight
    elif comp_cmd == "Q":
        q_comp = -comp_weight

    q_total = q_pid + q_comp
    # [-1, 1] 범위로 클램프
    q_total = max(-1.0, min(1.0, q_total))

    # 다시 Q/E + weight로 변환
    if abs(q_total) < 1e-3:
        QE_command, QE_weight = "", 0.0
    elif q_total > 0:
        QE_command, QE_weight = "E", abs(q_total)
    else:
        QE_command, QE_weight = "Q", abs(q_total)

    # ===== PITCH: 기존 PID 그대로 유지 =====
    pitch_control = turret_pitch_pid.compute(
        setpoint=0.0,
        measured_value=-pitch_angle_diff,
        dt=dt
    )
    RF_command, RF_weight = map_pitch_control_to_RF(pitch_control)

    return QE_command, QE_weight, RF_command, RF_weight, yaw_angle_diff, pitch_angle_diff, distance_xz


def turret_control(enemy_detection, enemy_in_fov,
                   player_x, player_y, player_z,
                   player_turret_x, player_turret_y,
                   enemy_x, enemy_y, enemy_z,
                   dt):
    global global_AD_command, global_AD_weight
    """
    포탑 제어 함수 (PID 스테빌라이저 + 발사 판단)
    - enemy_detection / enemy_in_fov 를 외부에서 그대로 받아서 사용
    - in_fov 여부와 웨이포인트 유무에 따라 조준 타겟을 선택
    """
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
            turret_yaw_pid.reset()
            turret_pitch_pid.reset()    
            return QE_command, QE_weight, RF_command, RF_weight, fire_command

    # 2) 선택된 타겟을 향해 PID 스테빌라이저 동작
    QE_command, QE_weight, RF_command, RF_weight, \
        yaw_err, pitch_err, dist_xz = stabilizer(
            player_x, player_y, player_z,
            player_turret_x, player_turret_y,
            target_x, target_y, target_z,
            global_AD_command, global_AD_weight,  # 차체 회전에 대한 보상
            dt
        )

    # 3) 발사 판단 로직(필요하면 복구)
    # fire_command = fire_calculation(yaw_err, pitch_err, dist_xz) if (enemy_detection and enemy_in_fov) else False

    # 디버그 로그 예시
    print(f"[Turret] yaw_err={yaw_err:.2f}, pitch_err={pitch_err:.2f}, dist={dist_xz:.1f}, "
          f"QE={QE_command}({QE_weight:.2f}), RF={RF_command}({RF_weight:.2f}), fire={fire_command}")

    return QE_command, QE_weight, RF_command, RF_weight, fire_command


def body_control(player_x, player_z, player_body_x):  # 차체 제어 함수
    # path = path_finding() # 경로 탐색 함수 (현재는 waypoints 직접 사용)
    WS_command, WS_weight, AD_command, AD_weight = path_tracking(player_x, player_z, player_body_x)
    return WS_command, WS_weight, AD_command, AD_weight


# --------------------------------------------------------------------
# Flask
# --------------------------------------------------------------------
app = Flask(__name__)  # Flask 앱 생성

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
    # distance = data["distance"]  # 필요시 사용

    # dt 계산 (시뮬레이터 시간 기준)
    dt = 0.03  # fallback 기본값
    if prev_time is not None:
        dt_candidate = time_val - prev_time
        if dt_candidate > 0:
            dt = dt_candidate
    prev_time = time_val

    # 플레이어 정보
    player_x = data["playerPos"]["x"]
    player_y = data["playerPos"]["y"]
    player_z = data["playerPos"]["z"]

    player_speed = data.get("playerSpeed", 0.0)  # 신뢰도가 낮다고 했으므로 보조값
    player_health = data.get("playerHealth", 100)

    player_turret_x = data["playerTurretX"]
    player_turret_y = data["playerTurretY"]
    player_body_x   = data["playerBodyX"]
    player_body_y   = data["playerBodyY"]
    player_body_z   = data["playerBodyZ"]

    # 적 정보
    enemy_x = data["enemyPos"]["x"]
    enemy_y = data["enemyPos"]["y"]
    enemy_z = data["enemyPos"]["z"]

    enemy_speed = data.get("enemySpeed", 0.0)
    enemy_health = data.get("enemyHealth", 100)
    enemy_turret_x = data.get("enemyTurretX", 0.0)
    enemy_turret_y = data.get("enemyTurretY", 0.0)
    enemy_body_x   = data.get("enemyBodyX", 0.0)
    enemy_body_y   = data.get("enemyBodyY", 0.0)
    enemy_body_z   = data.get("enemyBodyZ", 0.0)

    # detect 플래그를 외부에서 받는다고 가정 (없으면 기본값 유지)
    enemy_detection = data.get("enemyDetection", enemy_detection)
    enemy_in_fov    = data.get("enemyInFov",    enemy_in_fov)

    # Body Control (크로스 커플 포함)
    global_WS_command, global_WS_weight, \
    global_AD_command, global_AD_weight = body_control(
        player_x, player_z, player_body_x
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


@app.route('/get_action', methods=['POST'])
def get_action():
    global global_QE_command, global_QE_weight, global_RF_command, global_RF_weight  # turret
    global global_WS_command, global_WS_weight, global_AD_command, global_AD_weight  # body
    global global_fire_command  # fire

    # 기존에 계산된 명령어와 가중치에 따라 행동 결정
    action = {
        "moveWS":   {"command": global_WS_command, "weight": global_WS_weight},
        "moveAD":   {"command": global_AD_command, "weight": global_AD_weight},
        "turretQE": {"command": global_QE_command, "weight": global_QE_weight},
        "turretRF": {"command": global_RF_command, "weight": global_RF_weight},
        "fire":     global_fire_command
    }
    return jsonify(action)


@app.route('/update_obstacle', methods=['POST'])
def update_obstacle():
    print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!UPDATE OBSTACLE CALLED!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "No JSON received"}), 400

    obstacle_auto_planning_and_generate_circle_nodes(data["obstacles"])
    return jsonify({"status": "OK"})


# Endpoint called when the episode starts
@app.route('/init', methods=['GET'])
def init():
    config = {
        "startMode": "start",  # Options: "start" or "pause"
        "blStartX": starting_point[0],  # Blue Start Position
        "blStartY": starting_point[1],
        "blStartZ": starting_point[2],
        "rdStartX": 0,  # Red Start Position
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


if __name__ == '__main__':
    # 필요 시, Flask 디버그 옵션 조절 가능
    app.run(host='0.0.0.0', port=5000)
