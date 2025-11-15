from flask import Flask, request, jsonify
import heapq, math, threading, sys, logging

# ================================================================
# Tank Control Server (Line-of-Sight Path + Pure Pursuit + CLI)
# - 터미널에 "x z" 입력 → 목표 설정 → 경로계획
# - /info 주기 호출 시, 장애물/전차 자세 갱신 → 도착 시 다음 목표 입력 대기
# - A*: 가시선(Line-of-Sight) 단순화로 직선 위주 경로
# - 조향: Pure-Pursuit + 데드밴드/히스테리시스 → 꿈틀거림 최소화
# - 목표 도착: x,z 각각 ±2 안에 들어오면 도착 처리
# - 아군 시작: (50,50) / 적: (200,200)
# ================================================================

GRID_W, GRID_H = 300, 300

# --- Path follower tuning ---
REACH_DIST       = 1.5      # 웨이포인트 통과 반경
GOAL_TOL_XZ      = 2.0      # 목표 도착 축 기준 허용 오차 (±2)
TURN_STRONG_DEG  = 15.0     # 강회전 임계
TURN_FINE_DEG    = 1.5      # 미세회전 임계
WS_SPEED         = 0.6      # 정상 전진 속도 가중치
MIN_FWD_SPEED    = 0.22     # 회전 중에도 약간 전진 유지
LOOKAHEAD_DIST   = 8.0      # Pure Pursuit 룩어헤드 거리

# --- Heading basis / yaw alignment ---
ATAN2_BASIS      = "Z0"     # "Z0": atan2(dx,dz)에서 +Z가 0°, "X0": atan2(dz,dx)에서 +X가 0°
YAW_OFFSET_DEG   = 0.0      # 시뮬레이터 yaw 기준과의 오프셋 보정
YAW_INVERT       = False    # yaw 방향 반전 필요 시 True

# --- Replanning ---
REPLAN_LOOKAHEAD_STEPS = 15
ALLOW_DIAGONAL         = True
OBSTACLE_INFLATION     = 0

# --- Steering stabilization ---
STEER_DEADBAND   = 0.8
STEER_HYST       = 0.6
MAX_STEER_WEIGHT = 1.0
MID_STEER_WEIGHT = 0.35

# --- Quiet HTTP logs ---
QUIET_HTTP = True

app = Flask(__name__)

# ---------------------- Global State ----------------------------
pose = {"x": 50.0, "z": 50.0, "yaw": 0.0}       # 아군 시작 (50,50)
enemy = {"x": 200.0, "z": 200.0, "alive": True} # 적 고정 (200,200)

obstacles    = set()     # {(x,y),...} grid
goal         = None      # (x,y) grid
path         = []        # [(x,y), ...] grid
waypoint_idx = 0

last_WS = ("", 0.0)
last_AD = ("", 0.0)
last_QE = ("", 0.0)
last_RF = ("", 0.0)
last_fire = False

controller_state = {"last_sign": 0}  # -1/0/+1 (조향 히스테리시스)

goal_lock  = threading.Lock()
print_lock = threading.Lock()

# ------------------------- Utils --------------------------------
def qprint(*args, **kwargs):
    with print_lock:
        print(*args, **kwargs); sys.stdout.flush()

def clamp(v, a, b): return a if v < a else b if v > b else v

def world_to_grid(x: float, z: float):
    xi = int(round(x)); yi = int(round(z))
    return clamp(xi, 0, GRID_W-1), clamp(yi, 0, GRID_H-1)

def ang_diff_deg(a, b):
    # 차이 = (a - b) 를 [-180,180)로 정규화
    return (a - b + 180) % 360 - 180

def target_heading(dx, dz):
    if ATAN2_BASIS == "Z0":
        return math.degrees(math.atan2(dx, dz)) % 360
    else:
        return math.degrees(math.atan2(dz, dx)) % 360

def effective_yaw_deg(raw_yaw):
    y = -raw_yaw if YAW_INVERT else raw_yaw
    y = (y + YAW_OFFSET_DEG) % 360
    return y

def inflate_cells(cells, k):
    if k <= 0: return set(cells)
    out = set(cells)
    for (x,y) in list(cells):
        for dx in range(-k, k+1):
            for dy in range(-k, k+1):
                nx, ny = x+dx, y+dy
                if 0 <= nx < GRID_W and 0 <= ny < GRID_H:
                    out.add((nx,ny))
    return out

# --------------------------- A* ---------------------------------
def neighbors(x, y):
    steps = [(-1,0),(1,0),(0,-1),(0,1)]
    if ALLOW_DIAGONAL:
        steps += [(-1,-1),(-1,1),(1,-1),(1,1)]
    for dx, dy in steps:
        nx, ny = x+dx, y+dy
        if 0 <= nx < GRID_W and 0 <= ny < GRID_H:
            yield nx, ny

def heuristic(a, b):
    (x1,y1), (x2,y2) = a, b
    if ALLOW_DIAGONAL:
        dx, dy = abs(x1-x2), abs(y1-y2)
        D, D2 = 1.0, math.sqrt(2.0)
        return D*(dx+dy) + (D2-2*D)*min(dx,dy)
    else:
        return abs(x1-x2) + abs(y1-y2)

def astar(start, goal, obstacles_set):
    if start == goal: return [start]
    blocked = set(obstacles_set)
    if start in blocked or goal in blocked: return []
    D2 = math.sqrt(2.0)
    g = {start: 0.0}
    f = {start: heuristic(start, goal)}
    came = {}
    pq = [(f[start], start)]
    seen = set()
    while pq:
        _, cur = heapq.heappop(pq)
        if cur in seen: continue
        seen.add(cur)
        if cur == goal:
            pth = [cur]
            while cur in came:
                cur = came[cur]
                pth.append(cur)
            pth.reverse()
            return pth
        cx, cy = cur
        for nx, ny in neighbors(cx, cy):
            if (nx,ny) in blocked: continue
            cost = D2 if (nx!=cx and ny!=cy) else 1.0
            ng = g[cur] + cost
            if ng < g.get((nx,ny), 1e18):
                came[(nx,ny)] = cur
                g[(nx,ny)] = ng
                f[(nx,ny)] = ng + heuristic((nx,ny), goal)
                heapq.heappush(pq, (f[(nx,ny)], (nx,ny)))
    return []

# ---------------- LOS simplification (직선화) --------------------
def bresenham_line(x0, y0, x1, y1):
    """정수 격자에서 (x0,y0)->(x1,y1)까지 모든 셀을 생성."""
    dx = abs(x1 - x0); sx = 1 if x0 < x1 else -1
    dy = -abs(y1 - y0); sy = 1 if y0 < y1 else -1
    err = dx + dy
    x, y = x0, y0
    while True:
        yield (x, y)
        if x == x1 and y == y1: break
        e2 = 2 * err
        if e2 >= dy:
            err += dy; x += sx
        if e2 <= dx:
            err += dx; y += sy

def line_blocked(p0, p1, blocked_cells):
    """p0->p1 직선 경로 중간에 장애물이 있으면 True."""
    x0, y0 = p0; x1, y1 = p1
    for c in bresenham_line(x0, y0, x1, y1):
        if c in blocked_cells and c not in (p0, p1):
            return True
    return False

def simplify_path_los(path_points, blocked_cells):
    """A* 경로를 가시선 가능한 코너만 남기도록 단순화."""
    if not path_points: return []
    simp = [path_points[0]]
    i = 0
    while i < len(path_points) - 1:
        j = i + 1
        while j + 1 < len(path_points) and not line_blocked(path_points[i], path_points[j+1], blocked_cells):
            j += 1
        simp.append(path_points[j])
        i = j
    return simp

# -------------------- Path & Replanning -------------------------
def need_replan_from_pose(px, pz):
    global path, waypoint_idx, obstacles, goal
    if goal is None: return False
    if not path or waypoint_idx >= len(path): return True
    next_cell = path[waypoint_idx]
    if next_cell in obstacles: return True
    end = min(len(path), waypoint_idx + REPLAN_LOOKAHEAD_STEPS)
    for i in range(waypoint_idx, end):
        if path[i] in obstacles:
            return True
    return False

def do_replan_from_pose(px, pz):
    global path, waypoint_idx, obstacles, goal
    sx, sy = world_to_grid(px, pz)
    gx, gy = goal
    inflated = inflate_cells(obstacles, OBSTACLE_INFLATION)
    new_path = astar((sx,sy), (gx,gy), inflated)
    if new_path:
        # 🔸 가시선 단순화로 직선 위주 경로
        new_path = simplify_path_los(new_path, set(inflated))
        path = new_path
        waypoint_idx = 0
        return True, len(path)
    return False, 0

def advance_waypoint_if_reached(px, pz):
    global waypoint_idx, path
    if not path or waypoint_idx >= len(path): return
    tx, ty = path[waypoint_idx]
    if math.hypot(tx - px, ty - pz) <= REACH_DIST:
        waypoint_idx = min(waypoint_idx + 1, len(path)-1)

def goal_reached(px, pz):
    if goal is None: return False
    gx, gy = goal
    return (abs(gx - px) <= GOAL_TOL_XZ) and (abs(gy - pz) <= GOAL_TOL_XZ)

def clear_current_plan():
    global goal, path, waypoint_idx
    goal = None
    path = []
    waypoint_idx = 0

# ----------------- Pure Pursuit: pick lookahead -----------------
def pick_lookahead_target(px, pz):
    """경로에서 현재 위치로부터 LOOKAHEAD_DIST 이상 떨어진 첫 점을 타겟으로 선택."""
    global path, waypoint_idx
    if not path: return None
    best = path[-1]
    for i in range(waypoint_idx, len(path)):
        tx, ty = path[i]
        if math.hypot(tx - px, ty - pz) >= LOOKAHEAD_DIST:
            best = (tx, ty)
            break
    return best

# ------------------------ Body control --------------------------
def compute_body_command(px, pz, yaw_deg):
    WS_command, WS_weight, AD_command, AD_weight = "", 0.0, "", 0.0
    if not path or waypoint_idx >= len(path):
        return WS_command, WS_weight, AD_command, AD_weight

    # 🔸 룩어헤드 타겟
    target = pick_lookahead_target(px, pz)
    if target is None:
        tx, ty = path[waypoint_idx]
    else:
        tx, ty = target

    dx = tx - px
    dz = ty - pz
    desired = target_heading(dx, dz)
    err = ang_diff_deg(desired, yaw_deg)  # (목표 - 현재) [-180,180)
    abs_err = abs(err)

    # 🔸 데드밴드 + 히스테리시스
    sign = 0
    if abs_err > STEER_DEADBAND:
        sign = 1 if err > 0 else -1
        if controller_state["last_sign"] != 0 and sign != controller_state["last_sign"]:
            if abs_err < (STEER_DEADBAND + STEER_HYST):
                sign = controller_state["last_sign"]  # 이전 방향 유지
    controller_state["last_sign"] = sign

    # 🔸 회전/전진 결합
    if sign == 0:
        WS_command, WS_weight = "W", WS_SPEED
        AD_command, AD_weight = "", 0.0
    else:
        if abs_err > TURN_STRONG_DEG:
            AD_command, AD_weight = ("D", MAX_STEER_WEIGHT) if sign > 0 else ("A", MAX_STEER_WEIGHT)
            WS_command, WS_weight = "W", MIN_FWD_SPEED
        elif abs_err > TURN_FINE_DEG:
            AD_command, AD_weight = ("D", MID_STEER_WEIGHT) if sign > 0 else ("A", MID_STEER_WEIGHT)
            WS_command, WS_weight = "W", max(MIN_FWD_SPEED, WS_SPEED * 0.65)
        else:
            WS_command, WS_weight = "W", WS_SPEED
            AD_command, AD_weight = "", 0.0

    return WS_command, WS_weight, AD_command, AD_weight

# ------------------------ Internal helpers ----------------------
def set_goal_world(gx, gz):
    """터미널/HTTP 공용 목표 설정 (world → grid)"""
    global goal
    with goal_lock:
        goal = world_to_grid(float(gx), float(gz))
    qprint(f"🎯 Goal set to {goal[0]},{goal[1]}")

def try_plan_from_current_pose():
    if pose["x"] is None or pose["z"] is None or goal is None:
        qprint("⏳ Waiting for pose or goal to be available (/info).")
        return False
    ok, plen = do_replan_from_pose(pose["x"], pose["z"])
    if ok: qprint(f"🗺️  Planned: {plen} steps from current pose.")
    else:  qprint("❌ No path found (check obstacles/goal).")
    return ok

# ----------------------------- API ------------------------------
@app.route("/init", methods=["GET"])
def init():
    cfg = {
        "startMode": "start",
        "trackingMode": True,
        "detactMode": False,
        "enemyTracking": False,
        "logMode": True,
        "saveSnapshot": False,
        "saveLog": True,
        "saveLidarData": False,
        "lux": 30000,
        # ✅ 아군 시작 위치를 50,50으로 고정
        "blStartX": 50, "blStartY": 10, "blStartZ": 50,
        # 레드(적) 시작 위치는 시뮬레이터용 데코 (서버 내부 enemy와는 별개)
        "rdStartX": 300, "rdStartY": 10, "rdStartZ": 150
    }
    return jsonify(cfg)

@app.route("/start", methods=["GET"])
def start():
    return jsonify({"control": ""})

@app.route("/set_goal", methods=["POST"])
def set_goal_api():
    data = request.get_json(silent=True) or {}
    def to_float(v):
        try: return float(v)
        except: return None
    gx = gz = None
    if "x" in data and "z" in data:
        gx, gz = to_float(data["x"]), to_float(data["z"])
    elif "goal" in data:
        g = data["goal"]
        if isinstance(g, (list, tuple)) and len(g) >= 2:
            gx, gz = to_float(g[0]), to_float(g[1])
        elif isinstance(g, dict) and "x" in g and "z" in g:
            gx, gz = to_float(g["x"]), to_float(g["z"])
    if gx is None or gz is None:
        return jsonify({"ok": False, "error": "Use {'x':..,'z':..} or {'goal':[x,z]}"}), 400
    set_goal_world(gx, gz)
    try_plan_from_current_pose()
    return jsonify({"ok": True, "goal_grid": list(goal)})

@app.route("/update_obstacles", methods=["POST"])
def update_obstacles():
    global obstacles
    data = request.get_json(silent=True) or {}
    if "cells" in data:
        cells = [tuple(world_to_grid(p[0], p[1])) for p in data["cells"]]
        obstacles = set(cells)
    else:
        for k in ("add","remove"):
            lst = data.get(k, [])
            cells = [tuple(world_to_grid(p[0], p[1])) for p in lst]
            if k == "add": obstacles |= set(cells)
            else:          obstacles -= set(cells)
    return jsonify({"ok": True, "count": len(obstacles)})

@app.route("/update_obstacle", methods=["POST"])
def update_obstacle_alias():
    return update_obstacles()

@app.route("/clear_obstacles", methods=["POST"])
def clear_obstacles():
    global obstacles
    obstacles.clear()
    return jsonify({"ok": True})

@app.route("/plan", methods=["POST"])
def plan():
    global goal
    data = request.get_json(silent=True) or {}
    if "goal" in data:
        g = data["goal"]
        if isinstance(g, (list, tuple)) and len(g) >= 2:
            set_goal_world(g[0], g[1])
        elif isinstance(g, dict) and "x" in g and "z" in g:
            set_goal_world(g["x"], g["z"])
    if goal is None:
        return jsonify({"error":"set goal first"}), 400
    ok = try_plan_from_current_pose()
    if not ok:
        return jsonify({"error":"no path found"}), 409
    return jsonify({"ok": True, "path_len": len(path)})

@app.route("/info", methods=["POST"])
def info():
    global last_WS, last_AD, last_QE, last_RF, last_fire
    data = request.get_json(force=True) or {}

    # 아군 pose 갱신
    ppos = data.get("playerPos", {})
    if "x" in ppos: pose["x"] = float(ppos["x"])
    if "z" in ppos: pose["z"] = float(ppos["z"])
    if "playerBodyX" in data:
        pose["yaw"] = effective_yaw_deg(float(data["playerBodyX"]))

    # 장애물 병합
    if "obstacles" in data and data["obstacles"]:
        add_cells = [tuple(world_to_grid(p[0], p[1])) for p in data["obstacles"]]
        for c in add_cells: obstacles.add(c)

    # 도착 판정
    reached = False
    if goal is not None and pose["x"] is not None:
        if goal_reached(pose["x"], pose["z"]):
            gx, gy = goal
            clear_current_plan()
            last_WS = ("", 0.0); last_AD = ("", 0.0)
            reached = True
            qprint(f"✅ Goal reached ({gx},{gy}). Enter next goal (x z):")

    # 진행 중이면 필요 시 재계획 & 제어
    if not reached:
        if path and waypoint_idx < len(path) and pose["x"] is not None:
            advance_waypoint_if_reached(pose["x"], pose["z"])
        if goal is not None and need_replan_from_pose(pose["x"], pose["z"]):
            do_replan_from_pose(pose["x"], pose["z"])
        if pose["yaw"] is not None and pose["x"] is not None:
            ws_cmd, ws_w, ad_cmd, ad_w = compute_body_command(pose["x"], pose["z"], pose["yaw"])
            last_WS = (ws_cmd, ws_w); last_AD = (ad_cmd, ad_w)

    return jsonify({"ok": True, "goal_reached": reached})

@app.route("/get_action", methods=["POST"])
def get_action():
    return jsonify({
        "moveWS":  {"command": last_WS[0], "weight": last_WS[1]},
        "moveAD":  {"command": last_AD[0], "weight": last_AD[1]},
        "turretQE":{"command": last_QE[0], "weight": last_QE[1]},
        "turretRF":{"command": last_RF[0], "weight": last_RF[1]},
        "fire":     last_fire
    })

@app.route("/status", methods=["GET"])
def status():
    next_wp = None
    if path and waypoint_idx < len(path):
        tx, ty = path[waypoint_idx]; next_wp = {"x": tx, "z": ty}
    return jsonify({
        "pose": pose,
        "goal": list(goal) if goal else None,
        "path_len": len(path),
        "waypoint_idx": waypoint_idx,
        "next_wp": next_wp,
        "enemy": enemy,
        "obstacles_count": len(obstacles)
    })

# -------------------------- CLI Thread --------------------------
def cli_loop():
    qprint("▶ Enter goal as: x z   (e.g., 280 280)")
    qprint("   Tips: adjust YAW_OFFSET_DEG / YAW_INVERT / ATAN2_BASIS if heading feels off.")
    while True:
        try:
            line = input("> ").strip()
        except EOFError:
            break
        if not line:
            continue
        if line.lower() in ("q", "quit", "exit"):
            qprint("Bye."); break
        parts = line.replace(",", " ").split()
        if len(parts) < 2:
            qprint("Format: x z   (e.g., 280 280)"); continue
        try:
            gx, gz = float(parts[0]), float(parts[1])
        except:
            qprint("Numbers only. Example: 280 280"); continue
        set_goal_world(gx, gz)
        try_plan_from_current_pose()

# ---------------------------- Main ------------------------------
if __name__ == "__main__":
    if QUIET_HTTP:
        logging.getLogger('werkzeug').setLevel(logging.ERROR)
        app.logger.disabled = True

    threading.Thread(target=cli_loop, daemon=True).start()

    qprint("Tank Server (LOS + PurePursuit + CLI) on 0.0.0.0:5000")
    qprint("Type goals here while simulator runs. Example: 280 280")
    app.run(host="0.0.0.0", port=5000)
