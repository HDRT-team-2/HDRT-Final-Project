from flask import Flask, request, jsonify
import math
import heapq
import time
from typing import List, Tuple, Set

# -------------------------------------------------------------------
# detect | Integrated Battlefield Situation Management (IBSM)
enemy_detection, enemy_in_fov = False, False # detect API

# info, get_action | Tank Body Movement Control
global_WS_command, global_WS_weight, global_AD_command, global_AD_weight = "", 0.0, "", 0.0
starting_point = [10,10,10]

# [MOD] NEW: 마지막으로 알려진 탱크의 격자 좌표 (경로 재탐색 시 시작점으로 사용)
last_player_pos_grid = (starting_point[0], starting_point[2])

# -------------------------------------------------------------------
# info | Waypoint : Linked List
class WaypointNode:
    def __init__(self, x, z, target_x, target_z):
        self.x = float(x) # pos x
        self.z = float(z) # pos z
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

# /info 루프용 이전 시간
prev_time = None

# Path Planning
waypoints = WaypointList()

# ------------------ A* Path Planner (integrated) -------------------
# constants for offline planner (used to produce waypoints)
GRID_W, GRID_H = 300, 300        # 300 x 300 (1셀 = 1 단위)
ALLOW_DIAGONAL = True            # 8방향
OBST_SIZE      = 20              # 장애물 한 변 길이 (정사각형)  (used if needed)
OBST_HALF      = OBST_SIZE // 2  # 10
CLEARANCE      = 3               # 장애물과 최소거리 3칸(팽창 반경)
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

def astar(start: Tuple[int,int], goal: Tuple[int,int], blocked: Set[Tuple[int,int]]) -> List[Tuple[int,int]]:
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
            step_cost = D2 if (nx != cx and ny != cy) else 1.0
            ng = g[cur] + step_cost
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

# helper: clear current waypoints and fill with given path list (list of (x,y) ints)
def fill_waypoints_from_path(path_points: List[Tuple[int,int]]):
    waypoints.clear()
    for p in path_points:
        # convert grid (x,y) -> use x as x, y as z in your existing waypoint coords
        waypoints.append(float(p[0]), float(p[1]), float(p[0]), float(p[1]))
# --------------------------------------------------------------------

def obstacle_auto_planning_and_generate_circle_nodes(obstacles):
    global last_player_pos_grid # [MOD] 동적 시작점을 가져오기 위해 전역 변수 선언

    # existing circle-based behavior (unchanged)

    # --- NEW: build A* blocked grid from provided obstacles and create a simplified path as alternative waypoints ---
    # construct centers from provided obstacle boxes (use their center rounded to int grid)
    centers = []
    for obs in obstacles:
        cx = int(round((obs['x_min'] + obs['x_max']) / 2.0))
        cz = int(round((obs['z_min'] + obs['z_max']) / 2.0))
        centers.append((cx, cz))

    # build blocked set with inflation (OBST_HALF + CLEARANCE)
    blocked_inflated: Set[Tuple[int, int]] = set()
    infl_half = OBST_HALF + CLEARANCE
    for (cx, cz) in centers:
        stamp_square(blocked_inflated, cx, cz, infl_half)

    # run A*
    # [MOD] A* 시작점을 정적 START_GRID 대신 현재 위치(last_player_pos_grid)로 변경
    current_start_grid = last_player_pos_grid 

    path = astar(current_start_grid, GOAL_GRID, blocked_inflated) # [MOD]
    if path:
        path2 = simplify_path_los(path, blocked_inflated)
        # convert to waypoints (clear existing and add this path)
        fill_waypoints_from_path(path2)
        print(f"A* 기반으로 생성된 waypoints 수: {len(path2)} (시작점: {current_start_grid})") # [MOD] 디버그 로그 추가
        print(f'헤딩 웨이포인트 : {path2}')
    else:
        print("A* 경로를 찾지 못했습니다 (update_obstacle).")

# 여기까지 TPP 부분이지 ------------------------------------------------------


# 이거는 ADCS 부분이지 ---------------------

def path_tracking(player_x, player_z, player_body_x):
    print("path_tracking")

    # 초기화
    WS_command, WS_weight, AD_command, AD_weight = "", 0.0, "", 0.0

    # 1. 현재 웨이포인트 선택
    current_waypoint = waypoints.peek()
    if current_waypoint is None:
        WS_command, WS_weight = "STOP", 1.0
        return WS_command, WS_weight, AD_command, AD_weight

    # waypoint에 대한 엄격한 도달을 제거
    # 지나쳤으면 그냥 다음 노드로 넘어갈 수 있도록 동적 처리
    while True:
        dx = current_waypoint.x - player_x
        dz = current_waypoint.z - player_z
        distance = math.sqrt(dx*dx + dz*dz)

        print("Distance to Waypoint:", distance)

        # 도달 판정 완화
        # 기존: <= 1.0이면 도달 → 너무 촘촘함
        # 개선: <= 8.0m 안에 들어오면 도달로 간주하고 다음 노드로
        if distance <= 8.0:
            print("=== REACHED (SOFT) WAYPOINT ===")
            waypoints.pop()
            current_waypoint = waypoints.peek()
            if current_waypoint is None:
                WS_command, WS_weight = "STOP", 1.0
                return WS_command, WS_weight, AD_command, AD_weight
            continue  # 다음 waypoint 체크
        break

    # 다음 waypoint 기준
    dx = current_waypoint.x - player_x
    dz = current_waypoint.z - player_z
    target_angle = math.degrees(math.atan2(dx, dz)) % 360

    # 현재 차체 yaw
    angle_diff = (target_angle - player_body_x + 540) % 360 - 180
    abs_angle_diff = abs(angle_diff)

    # 각도 차이 기반 속도 조절
    #    - 큰 각도일수록 속도를 자동 감속
    #    - 각도가 0에 가까우면 가속
    #    - 이 부분이 “WS–AD 커플링”의 핵심
    angle_norm = min(abs_angle_diff / 90.0, 1.0)  # 0~1
    # angle_norm이 크면 회전 필요 → 속도 줄임
    # angle_norm이 작으면 직진 → 속도 증가
    forward_weight = 0.6 * (1.0 - angle_norm)  # 0.0 ~ 0.6 사이

    # 최대 전진 속도 제한 (40km/h→ weight=40/65≈0.61)
    max_forward_weight =40.0 / 65.0
    forward_weight = min(forward_weight, max_forward_weight)

    # 회전 명령 (AD)
    if abs_angle_diff > 10:
        # 큰 각도면 회전 강하게
        turn_weight = min(abs_angle_diff / 60.0, 1.0)
        if angle_diff > 0:
            AD_command, AD_weight = "D", turn_weight
        else:
            AD_command, AD_weight = "A", turn_weight
    else:
        # 각도 안정권이면 회전 입력 제거
        AD_command, AD_weight = "", 0.0

    # 전진 명령 (WS)
    # 회전 중이라도 forward_weight가 0이 아닌 이상 전진 유지
    if forward_weight > 0.05:
        WS_command, WS_weight = "W", forward_weight
    else:
        WS_command, WS_weight = "", 0.0

    return WS_command, WS_weight, AD_command, AD_weight

def body_control(player_x, player_z, player_body_x): # 차체 제어 함수
    # 초기화
    WS_command, WS_weight, AD_command, AD_weight = 0.0, 0.0, 0.0, 0.0
    print("body_control")
    # path = path_finding() # 경로 탐색 함수

    WS_command, WS_weight, AD_command, AD_weight = path_tracking(player_x, player_z, player_body_x)
    
    return WS_command, WS_weight, AD_command, AD_weight

# --------------------------------------------------------------------

app = Flask(__name__) # Flask 앱 생성
# --------------------------------------------------------------------

@app.route('/info', methods=['POST'])
def info():
    global global_WS_command, global_WS_weight, global_AD_command, global_AD_weight
    global enemy_detection, enemy_in_fov
    global prev_time
    global last_player_pos_grid # [MOD] 전역 변수 추가

    data = request.get_json(force=True)

    print('인포에서 받아온 정보 : ', data)
    if not data:
        return jsonify({"error": "No JSON received"}), 400

    time_val = data["time"]
    distance = data["distance"]

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

    # [MOD] NEW: 현재 위치를 격자 좌표로 변환하여 저장 (경로 재탐색을 위한 동적 시작점)
    # A*는 정수형 격자 좌표를 사용하므로, 반올림하여 정수형으로 변환합니다.
    last_player_pos_grid = (int(round(player_x)), int(round(player_z)))

    player_speed = data["playerSpeed"]
    player_health = data["playerHealth"]
    player_body_x = data["playerBodyX"]
    player_body_y = data["playerBodyY"]
    player_body_z = data["playerBodyZ"]

    # 적 정보
    enemy_x = data["enemyPos"]["x"]
    enemy_y = data["enemyPos"]["y"]
    enemy_z = data["enemyPos"]["z"]

    enemy_speed = data["enemySpeed"]
    enemy_health = data["enemyHealth"]
    enemy_body_x = data["enemyBodyX"]
    enemy_body_y = data["enemyBodyY"]
    enemy_body_z = data["enemyBodyZ"]

    # detect 플래그를 외부에서 받는다고 가정 (없으면 기본값 유지)
    enemy_detection = data.get("enemyDetection", enemy_detection)
    enemy_in_fov = data.get("enemyInFov", enemy_in_fov)

    # Body Control
    global_WS_command, global_WS_weight, \
        global_AD_command, global_AD_weight = body_control(
            player_x, player_z, player_body_x
        )
    return jsonify({"status": "success", "control": ""})

# --------------------------------------------------------------------

@app.route('/get_action', methods=['POST'])
def get_action():
    global global_WS_command, global_WS_weight, global_AD_command, global_AD_weight # body

    # 기존에 계산된 명령어와 가중치에 따라 행동 결정
    action = {
        "moveWS":  {"command": global_WS_command, "weight": global_WS_weight},
        "moveAD":  {"command": global_AD_command, "weight": global_AD_weight},
    }
    print('뱉어내는 웨이트값 : ', action)
    return jsonify(action)

# --------------------------------------------------------------------

@app.route('/update_obstacle', methods=['POST'])
def update_obstacle():
    print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!UPDATE OBSTACLE CALLED!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    data = request.get_json(force=True)

    print('장애물 받아온 정보 : ', data)

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
        "blStartX": starting_point[0],  #Blue Start Position
        "blStartY": starting_point[1],
        "blStartZ": starting_point[2],
        "rdStartX": 0, #Red Start Position
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
    # print("Initialization config sent via /init:", config)
    return jsonify(config)

# --------------------------------------------------------------------

@app.route('/start', methods=['GET'])
def start():
    # print("🚀 /start command received")
    return jsonify({"control": ""})

# --------------------------------------------------------------------

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)

# --------------------------------------------------------------------