from flask import Flask, request, jsonify
import heapq, math, threading, sys, logging
from collections import deque

# ================================================================
# Tank Control Server (LOS Path + Pure Pursuit + Multi-Goals + Dwell&Turn)
# - CLI로 여러 목표 입력 → 'ok' 입력 시 입력 순서대로 경유 주행
# - 도착 시: 잠깐 정지(DWELL) → 다음 목표 방향으로 제자리 회전(TURN_IN_PLACE) → 전진(CRUISE)
# - 가시선 단순화(Line-of-Sight)로 직선 위주 경로 / Pure-Pursuit 추종
# - 목표 도착 판정: x,z 각각 ±2
# - 아군 시작 (50,50), 적 (200,200)
# ================================================================

GRID_W, GRID_H = 300, 300

# --- Follower / control tuning ---
REACH_DIST       = 1.5
GOAL_TOL_XZ      = 2.0
WS_SPEED         = 0.6
MIN_FWD_SPEED    = 0.22
LOOKAHEAD_DIST   = 8.0

# --- Heading / yaw alignment ---
ATAN2_BASIS      = "Z0"   # or "X0"
YAW_OFFSET_DEG   = 0.0
YAW_INVERT       = False

# --- Turn-in-place thresholds ---
TURN_STRONG_DEG  = 15.0   # 강회전 임계
TURN_FINE_DEG    = 1.5    # 미세회전 임계
TURN_DONE_DEG    = 2.0    # 제자리 회전 완료 기준 (이 이내면 전진 모드로 전환)
MAX_STEER_WEIGHT = 1.0
MID_STEER_WEIGHT = 0.35

# --- Dwell (정지 대기) ---
DWELL_TICKS      = 6      # /info 주기 기준 정지 유지 틱 수

# --- Replanning ---
REPLAN_LOOKAHEAD_STEPS = 15
ALLOW_DIAGONAL         = True
OBSTACLE_INFLATION     = 0

# --- Quiet HTTP logs ---
QUIET_HTTP = True

app = Flask(__name__)

# ---------------------- Global State ----------------------------
pose = {"x": 50.0, "z": 50.0, "yaw": 0.0}
enemy = {"x": 200.0, "z": 200.0, "alive": True}

obstacles    = set()     # {(x,y),...} in grid
path         = []        # [(x,y), ...]
waypoint_idx = 0
goal         = None

# 멀티 목표 큐 (world 좌표, float)
goal_queue   = deque()

# 제어 출력 캐시
last_WS = ("", 0.0)
last_AD = ("", 0.0)
last_QE = ("", 0.0)
last_RF = ("", 0.0)
last_fire = False

# 상태 머신
mode = "CRUISE"          # "CRUISE" | "DWELL" | "TURN_IN_PLACE" | "IDLE"
dwell_counter = 0

# 동기화
goal_lock  = threading.Lock()
print_lock = threading.Lock()

def qprint(*args, **kwargs):
    with print_lock:
        print(*args, **kwargs); sys.stdout.flush()

# ------------------------- Utils --------------------------------
def clamp(v, a, b): return a if v < a else b if v > b else v

def world_to_grid(x: float, z: float):
    xi = int(round(x)); yi = int(round(z))
    return clamp(xi, 0, GRID_W-1), clamp(yi, 0, GRID_H-1)

def ang_diff_deg(a, b):
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

# ---------------- LOS simplification ----------------------------
def bresenham_line(x0, y0, x1, y1):
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
    x0, y0 = p0; x1, y1 = p1
    for c in bresenham_line(x0, y0, x1, y1):
        if c in blocked_cells and c not in (p0, p1):
            return True
    return False

def simplify_path_los(path_points, blocked_cells):
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

# ----------------- Pure Pursuit lookahead -----------------------
def pick_lookahead_target(px, pz):
    global path, waypoint_idx
    if not path: return None
    best = path[-1]
    for i in range(waypoint_idx, len(path)):
        tx, ty = path[i]
        if math.hypot(tx - px, ty - pz) >= LOOKAHEAD_DIST:
            best = (tx, ty)
            break
    return best

# --------------------- Body Controllers -------------------------
def compute_turn_only(px, pz, yaw_deg):
    """제자리 회전 모드: WS 비우고 AD만 출력."""
    if not path or waypoint_idx >= len(path):
        return ("", 0.0, "", 0.0)
    # 다음 목표 방향(룩어헤드 대신 바로 다음 waypoint 사용)
    tx, ty = path[waypoint_idx]
    dx = tx - px; dz = ty - pz
    desired = target_heading(dx, dz)
    err = ang_diff_deg(desired, yaw_deg)
    abs_err = abs(err)

    if abs_err <= TURN_DONE_DEG:
        # 회전 완료
        return ("", 0.0, "", 0.0)

    if abs_err > TURN_STRONG_DEG:
        ad_cmd, ad_w = ("D", MAX_STEER_WEIGHT) if err > 0 else ("A", MAX_STEER_WEIGHT)
    else:
        ad_cmd, ad_w = ("D", MID_STEER_WEIGHT) if err > 0 else ("A", MID_STEER_WEIGHT)

    return ("", 0.0, ad_cmd, ad_w)

def compute_cruise(px, pz, yaw_deg):
    """주행 모드: 회전+전진 병행 (Pure Pursuit)"""
    WS_command, WS_weight, AD_command, AD_weight = "", 0.0, "", 0.0
    if not path or waypoint_idx >= len(path):
        return WS_command, WS_weight, AD_command, AD_weight

    target = pick_lookahead_target(px, pz)
    if target is None:
        tx, ty = path[waypoint_idx]
    else:
        tx, ty = target

    dx, dz = tx - px, ty - pz
    desired = target_heading(dx, dz)
    err = ang_diff_deg(desired, yaw_deg)
    abs_err = abs(err)

    if abs_err > TURN_STRONG_DEG:
        AD_command, AD_weight = ("D", MAX_STEER_WEIGHT) if err > 0 else ("A", MAX_STEER_WEIGHT)
        WS_command, WS_weight = "W", MIN_FWD_SPEED
    elif abs_err > TURN_FINE_DEG:
        AD_command, AD_weight = ("D", MID_STEER_WEIGHT) if err > 0 else ("A", MID_STEER_WEIGHT)
        WS_command, WS_weight = "W", max(MIN_FWD_SPEED, WS_SPEED * 0.65)
    else:
        WS_command, WS_weight = "W", WS_SPEED
        AD_command, AD_weight = "", 0.0

    return WS_command, WS_weight, AD_command, AD_weight

# ------------------------ Goal helpers --------------------------
def set_goal_world(gx, gz):
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

def pop_next_goal_and_plan():
    """큐에서 다음 목표를 꺼내고 경로 계획. 성공 시 True."""
    global goal
    if not goal_queue:
        goal = None
        return False
    gx, gz = goal_queue.popleft()
    set_goal_world(gx, gz)
    return try_plan_from_current_pose()

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
        "blStartX": 50, "blStartY": 10, "blStartZ": 50,
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
    goal_queue.append((gx, gz))
    return jsonify({"ok": True, "queued": len(goal_queue)})

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
    data = request.get_json(silent=True) or {}
    # /plan으로도 큐에 누적 가능
    if "goal" in data:
        g = data["goal"]
        if isinstance(g, (list, tuple)) and len(g) >= 2:
            goal_queue.append((float(g[0]), float(g[1])))
        elif isinstance(g, dict) and "x" in g and "z" in g:
            goal_queue.append((float(g["x"]), float(g["z"])))
    # 현재 목표 없으면 하나 꺼내서 계획
    ok = True
    if goal is None:
        ok = pop_next_goal_and_plan()
        if ok:
            # 새 목표 시작 시: 정지 → 회전 → 주행 순서
            enter_dwell_then_turn()
    if not ok:
        return jsonify({"error":"no path found or empty queue"}), 409
    return jsonify({"ok": True, "path_len": len(path), "queued": len(goal_queue)})

@app.route("/info", methods=["POST"])
def info():
    global last_WS, last_AD, last_QE, last_RF, last_fire
    data = request.get_json(force=True) or {}

    # Pose 갱신
    ppos = data.get("playerPos", {})
    if "x" in ppos: pose["x"] = float(ppos["x"])
    if "z" in ppos: pose["z"] = float(ppos["z"])
    if "playerBodyX" in data:
        pose["yaw"] = effective_yaw_deg(float(data["playerBodyX"]))

    # 장애물 병합
    if "obstacles" in data and data["obstacles"]:
        add_cells = [tuple(world_to_grid(p[0], p[1])) for p in data["obstacles"]]
        for c in add_cells: obstacles.add(c)

    # 상태 업데이트
    state_machine_step()

    return jsonify({"ok": True, "mode": mode})

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
    cur_goal = list(goal) if goal else None
    return jsonify({
        "pose": pose,
        "goal": cur_goal,
        "path_len": len(path),
        "waypoint_idx": waypoint_idx,
        "next_wp": next_wp,
        "enemy": enemy,
        "obstacles_count": len(obstacles),
        "mode": mode,
        "queue_len": len(goal_queue)
    })

# ------------------------ State Machine -------------------------
def enter_dwell_then_turn():
    """도착 직후: 잠깐 정지 → 회전 모드로 전환"""
    global mode, dwell_counter, last_WS, last_AD
    mode = "DWELL"
    dwell_counter = DWELL_TICKS
    last_WS = ("", 0.0)
    last_AD = ("", 0.0)
    qprint("⏸️  Dwell...")

def state_machine_step():
    """각 /info 틱마다 호출: 모드에 따라 제어 출력 갱신"""
    global mode, dwell_counter, last_WS, last_AD
    if pose["x"] is None or pose["z"] is None or pose["yaw"] is None:
        last_WS, last_AD = ("", 0.0), ("", 0.0)
        return

    # 목표가 없고 큐도 없으면 IDLE
    if goal is None and not goal_queue:
        last_WS, last_AD = ("", 0.0), ("", 0.0)
        return

    # 목표가 없으면 큐에서 하나 꺼내고 계획
    if goal is None and goal_queue:
        if pop_next_goal_and_plan():
            enter_dwell_then_turn()
        else:
            last_WS, last_AD = ("", 0.0), ("", 0.0)
            return

    px, pz, yaw = pose["x"], pose["z"], pose["yaw"]

    # 도착 판정
    if goal is not None and goal_reached(px, pz):
        gx, gy = goal
        qprint(f"✅ Reached ({gx},{gy})")
        clear_current_plan()
        # 남은 큐가 있으면 다음 목표 준비
        if goal_queue:
            if pop_next_goal_and_plan():
                enter_dwell_then_turn()
        else:
            # 더 이상 갈 곳 없음 → 정지
            mode = "IDLE"
            last_WS, last_AD = ("", 0.0), ("", 0.0)
        return

    # 진행 중: 필요 시 웨이포인트 갱신/재계획
    if path and waypoint_idx < len(path):
        advance_waypoint_if_reached(px, pz)
    if goal is not None and need_replan_from_pose(px, pz):
        do_replan_from_pose(px, pz)

    # 모드별 제어
    if mode == "DWELL":
        last_WS, last_AD = ("", 0.0), ("", 0.0)
        dwell_counter -= 1
        if dwell_counter <= 0:
            mode = "TURN_IN_PLACE"
            qprint("🔄 Turn-in-place...")
        return

    if mode == "TURN_IN_PLACE":
        ws_cmd, ws_w, ad_cmd, ad_w = compute_turn_only(px, pz, yaw)
        last_WS, last_AD = (ws_cmd, ws_w), (ad_cmd, ad_w)
        # 회전 완료 조건: compute_turn_only가 WS/AD 모두 빈 명령 반환
        if ad_cmd == "" and ws_cmd == "":
            mode = "CRUISE"
            qprint("🏁 Heading aligned → CRUISE")
        return

    # 기본 주행
    mode = "CRUISE"
    ws_cmd, ws_w, ad_cmd, ad_w = compute_cruise(px, pz, yaw)
    last_WS, last_AD = (ws_cmd, ws_w), (ad_cmd, ad_w)

# -------------------------- CLI Thread --------------------------
def cli_loop():
    qprint("▶ 여러 목표를 줄마다 입력하세요:  x z")
    qprint("   입력을 끝냈으면 'ok' 입력 → 주행 시작")
    qprint("   예)\n       120 80\n       240 220\n       280 280\n       ok")
    qprint("------------------------------------------------------------")
    while True:
        try:
            line = input("> ").strip()
        except EOFError:
            break
        if not line:
            continue
        if line.lower() in ("q", "quit", "exit"):
            qprint("Bye."); break
        if line.lower() == "ok":
            # 현재 목표가 없으면 하나 꺼내 경로계획 + Dwell→Turn
            if goal is None:
                if pop_next_goal_and_plan():
                    enter_dwell_then_turn()
                else:
                    qprint("⚠️ 큐가 비어있습니다. 목표를 먼저 입력하세요.")
            else:
                qprint("이미 주행 중입니다.")
            continue
        parts = line.replace(",", " ").split()
        if len(parts) < 2:
            qprint("형식: x z   (예: 280 280)  또는 'ok'"); continue
        try:
            gx, gz = float(parts[0]), float(parts[1])
        except:
            qprint("숫자만 입력하세요. 예: 280 280"); continue
        goal_queue.append((gx, gz))
        qprint(f"➕ Buffered goal: ({gx},{gz}).  ('ok' 입력 시 주행 시작)")

# ---------------------------- Main ------------------------------
if __name__ == "__main__":
    if QUIET_HTTP:
        logging.getLogger('werkzeug').setLevel(logging.ERROR)
        app.logger.disabled = True

    threading.Thread(target=cli_loop, daemon=True).start()

    qprint("Tank Server (LOS + PurePursuit + CLI + Multi-Goals + Dwell&Turn) on 0.0.0.0:5000")
    qprint("여러 목표를 입력한 뒤 'ok'를 입력하면 입력 순서대로 경유 주행합니다.")
    app.run(host="0.0.0.0", port=5000)
