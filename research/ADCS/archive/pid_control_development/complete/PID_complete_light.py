# ==================================================================
#  PID_mid_light_complete — Option A 완성본
#  - 내부 로직, 내부 변수명 100% 원본 유지
#  - 연산(수학/로직) 절대 변경 없음
#  - A* 내부는 tuple, 반환은 dict(x,y,z)
#  - waypoint 구조 dict 기반 3D
#  - IBSM ↔ ADCS ↔ TPP 통신 dict 통일
#  - waypoint.y = player_y
# ==================================================================

from flask import Flask, request, jsonify
import math
import heapq

# ================================================================
# IBSM ↔ ADCS 글로벌 변수 (원본 구조 그대로 유지)
# ================================================================
enemy_detection, enemy_in_fov = False, False      # detect API

# movement
global_WS_command, global_WS_weight = "", 0.0
global_AD_command, global_AD_weight = "", 0.0

# 초기 시작점 (dict 기반)
starting_point = {"x": 10.0, "y": 10.0, "z": 10.0}

# ================================================================
# Waypoint Linked List (3D dict 구조 기반)
# ================================================================
class WaypointNode:
    def __init__(self, x, y, z):
        self.pos = {"x": float(x), "y": float(y), "z": float(z)}
        self.next = None

class WaypointList:
    def __init__(self):
        self.head = None
        self.tail = None
        self._len = 0

    def append(self, x, y, z):
        node = WaypointNode(x, y, z)
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

    def clear(self):
        self.head = None
        self.tail = None
        self._len = 0

    def to_list(self):
        """IBSM에게 보낼 때 사용하는 dict 리스트"""
        out = []
        cur = self.head
        while cur:
            out.append({
                "x": cur.pos["x"],
                "y": cur.pos["y"],
                "z": cur.pos["z"]
            })
            cur = cur.next
        return out


waypoints = WaypointList()
last_player_grid = (int(starting_point["x"]), int(starting_point["z"]))

# ================================================================
# A* PATH PLANNING (내부 계산 tuple 기반 100% 유지)
# ================================================================
GRID_W, GRID_H = 300, 300
ALLOW_DIAGONAL = True

OBST_SIZE = 20
OBST_HALF = OBST_SIZE // 2
CLEARANCE = 3
GOAL_GRID = (280, 280)


def in_bounds(x, y):
    return 0 <= x < GRID_W and 0 <= y < GRID_H


def neighbors(x, y):
    steps = [(-1,0),(1,0),(0,-1),(0,1)]
    if ALLOW_DIAGONAL:
        steps += [(-1,-1),(-1,1),(1,-1),(1,1)]
    for dx, dy in steps:
        nx, ny = x + dx, y + dy
        if in_bounds(nx, ny):
            yield nx, ny


def heuristic(a, b):
    (x1,y1), (x2,y2) = a, b
    dx, dy = abs(x1-x2), abs(y1-y2)
    if ALLOW_DIAGONAL:
        D = 1.0
        D2 = math.sqrt(2)
        return D*(dx+dy) + (D2-2*D)*min(dx, dy)
    return dx + dy


def stamp_square(blocked, cx, cz, half):
    x0, x1 = cx - half, cx + half - 1
    z0, z1 = cz - half, cz + half - 1
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            if in_bounds(x, z):
                blocked.add((x, z))


def astar(start, goal, blocked, player_y):
    """A* 내부 계산 tuple 기반 → 최종 반환 dict 기반(x,y,z). 연산 변경 없음."""
    # ---------------------------------------------------------
    # 기존 tuple 기반 A* 계산
    # ---------------------------------------------------------
    if start == goal:
        raw_path = [start]
    elif start in blocked or goal in blocked:
        raw_path = []
    else:
        D2 = math.sqrt(2)
        g = {start: 0.0}
        f = {start: heuristic(start, goal)}
        came = {}
        pq = [(f[start], start)]
        seen = set()
        raw_path = []

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
                raw_path = path
                break

            cx, cz = cur
            for nx, nz in neighbors(cx, cz):
                if (nx, nz) in blocked:
                    continue

                step = D2 if (nx != cx and nz != cz) else 1.0
                ng = g[cur] + step
                if ng < g.get((nx, nz), 1e18):
                    came[(nx, nz)] = cur
                    g[(nx, nz)] = ng
                    f[(nx, nz)] = ng + heuristic((nx, nz), goal)
                    heapq.heappush(pq, (f[(nx, nz)], (nx, nz)))

    # ---------------------------------------------------------
    # dict 기반 3D 변환 (연산 변경 없음)
    # ---------------------------------------------------------
    return [
        {"x": float(x), "y": float(player_y), "z": float(z)}
        for (x, z) in raw_path
    ]


# ================================================================
# LOS Simplify (tuple 기반 유지)
# ================================================================
def los_block(p0, p1, blocked):
    (x0,z0), (x1,z1) = p0, p1
    dx = abs(x1-x0)
    dz = abs(z1-z0)
    sx = 1 if x0 < x1 else -1
    sz = 1 if z0 < z1 else -1
    err = dx - dz

    x, z = x0, z0
    while True:
        if (x, z) in blocked and (x, z) not in (p0, p1):
            return True
        if x == x1 and z == z1:
            break

        e2 = err*2
        if e2 > -dz:
            err -= dz
            x += sx
        if e2 < dx:
            err += dx
            z += sz
    return False


def simplify_path(path, blocked):
    if not path:
        return []
    simp = [path[0]]
    i = 0
    while i < len(path)-1:
        j = i+1
        while j+1 < len(path) and not los_block(path[i], path[j+1], blocked):
            j += 1
        simp.append(path[j])
        i = j
    return simp


# ================================================================
# 장애물 기반 A* 경로 갱신 (dict 기반 waypoint 적용)
# ================================================================
def update_path(obstacles, player_y):
    global last_player_grid

    # 1) obstacle → blocked grid
    blocked = set()
    for obs in obstacles:
        cx = int(round((obs["x_min"] + obs["x_max"]) / 2))
        cz = int(round((obs["z_min"] + obs["z_max"]) / 2))
        stamp_square(blocked, cx, cz, OBST_HALF + CLEARANCE)

    # 2) tuple 기반 A*
    raw_dict_path = astar(last_player_grid, GOAL_GRID, blocked, player_y)

    # 3) waypoint 저장 (dict 기반)
    waypoints.clear()
    for p in raw_dict_path:
        waypoints.append(p["x"], p["y"], p["z"])


# ================================================================
# ADCS — Path Tracking (내부 로직 100% 원본 유지)
# ================================================================
def path_tracking(player_x, player_y, player_z, body_x):
    """
    원본 mid_light_complete 로직 100% 유지.
    dict는 외부에서만 사용하고 내부는 원본 변수명 그대로 사용.
    """
    global global_WS_command, global_WS_weight
    global global_AD_command, global_AD_weight

    # ------------------------------
    # Waypoint 추출
    # ------------------------------
    node = waypoints.peek()
    if not node:
        global_WS_command, global_WS_weight = "S", 1.0
        global_AD_command, global_AD_weight = "", 0.0
        return global_WS_command, global_WS_weight, global_AD_command, global_AD_weight

    # ------------------------------
    # 도달 체크 (원본 로직 유지)
    # ------------------------------
    while node:
        dx = node.pos["x"] - player_x
        dz = node.pos["z"] - player_z
        dist = math.sqrt(dx*dx + dz*dz)

        if dist <= 8.0:
            waypoints.pop()
            node = waypoints.peek()
            if not node:
                global_WS_command, global_WS_weight = "S", 1.0
                global_AD_command, global_AD_weight = "", 0.0
                return global_WS_command, global_WS_weight, global_AD_command, global_AD_weight
            continue
        break

    # ------------------------------
    # 방향 계산 (원본 그대로)
    # ------------------------------
    dx = node.pos["x"] - player_x
    dz = node.pos["z"] - player_z

    target_angle = math.degrees(math.atan2(dx, dz)) % 360
    diff = (target_angle - body_x + 540) % 360 - 180
    adiff = abs(diff)

    # ------------------------------
    # forward weight (원본 그대로)
    # ------------------------------
    ang_norm = min(adiff / 90.0, 1.0)
    forward = 0.6 * (1.0 - ang_norm)
    forward = min(forward, 40.0 / 65.0)

    # ------------------------------
    # turn weight (원본 그대로)
    # ------------------------------
    turn = 0.0
    if adiff > 10.0:
        turn = min(adiff / 60.0, 1.0)
        if diff > 0:
            global_AD_command = "D"
            global_AD_weight = turn
        else:
            global_AD_command = "A"
            global_AD_weight = turn
    else:
        global_AD_command, global_AD_weight = "", 0.0

    # ------------------------------
    # forward command (원본 그대로)
    # ------------------------------
    if forward > 0.05:
        global_WS_command = "W"
        global_WS_weight = forward
    else:
        global_WS_command, global_WS_weight = "", 0.0

    return global_WS_command, global_WS_weight, global_AD_command, global_AD_weight


# ================================================================
# Flask API
# ================================================================
app = Flask(__name__)


# ------------------------------------------------------------
# /get_tpp — IBSM → TPP
# ------------------------------------------------------------
@app.route("/get_tpp", methods=["POST"])
def get_tpp():
    global last_player_grid

    data = request.get_json()

    ally = data["ally_body_pos"]
    player_x, player_y, player_z = ally["x"], ally["y"], ally["z"]

    last_player_grid = (int(round(player_x)), int(round(player_z)))

    obstacles = []
    for u in data.get("unknowns", []):
        if u["unit_type"] == "obstacle":
            pos = u["position"]
            sz = 0.5
            obstacles.append({
                "x_min": pos["x"] - sz,
                "x_max": pos["x"] + sz,
                "z_min": pos["z"] - sz,
                "z_max": pos["z"] + sz
            })

    update_path(obstacles, player_y)

    return jsonify({
        "waypoints_list": waypoints.to_list(),
        "target_pos": data["target_pos"]
    })


# ------------------------------------------------------------
# /get_adcs — IBSM → ADCS
# ------------------------------------------------------------
@app.route("/get_adcs", methods=["POST"])
def get_adcs():
    data = request.get_json()

    ally = data["ally_body_pos"]
    player_x, player_y, player_z = ally["x"], ally["y"], ally["z"]

    body = data["ally_body_angle"]
    body_x = body["x"]

    WS_command, WS_weight, AD_command, AD_weight = path_tracking(player_x, player_y, player_z, body_x)

    # Option 1 — 내부는 그대로, 외부로 보낼 때 dict로 포장
    return jsonify({
        "moveWS": {"command": WS_command, "weight": WS_weight},
        "moveAD": {"command": AD_command, "weight": AD_weight}
    })


# ------------------------------------------------------------
# /info — 위치 업데이트
# ------------------------------------------------------------
@app.route("/info", methods=["POST"])
def info():
    global last_player_grid
    data = request.get_json()
    px = data["playerPos"]["x"]
    pz = data["playerPos"]["z"]
    last_player_grid = (int(round(px)), int(round(pz)))
    return jsonify({"status": "ok"})


# ------------------------------------------------------------
# /init — 시작 정보 전달
# ------------------------------------------------------------
@app.route("/init", methods=["GET"])
def init():
    return jsonify({
        "startMode": "start",
        "blStartX": starting_point["x"],
        "blStartY": starting_point["y"],
        "blStartZ": starting_point["z"]
    })


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
