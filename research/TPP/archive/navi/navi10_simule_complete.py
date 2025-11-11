from flask import Flask, request, jsonify
import math, heapq, threading

# ================== Config (World→Grid 스케일) ==================
SCALE                = 10                 # 1 world unit = 10 grid cells
WORLD_W, WORLD_H     = 300, 300          # 외부 API 단위
GRID_W, GRID_H       = WORLD_W*SCALE, WORLD_H*SCALE

ALLOW_DIAGONAL       = True               # 8방향
CLEARANCE_WORLD      = 3                  # 전차 충돌 여유(월드 단위)
CLEARANCE_GRID       = CLEARANCE_WORLD * SCALE

OBST_DEFAULT_SIZE    = 20                 # 디폴트 변(월드)
OBST_DEFAULT_RADIUS  = 10                 # 디폴트 반지름(월드)

app = Flask(__name__)

# ================== 상태 ==================
# 장애물은 "월드좌표" 파라미터로 등록; 내부 blocked-grid는 필요 시 갱신
obstacles = []   # [{ "type":"rect"|"circle",
                 #    "cx":float,"cz":float,
                 #    "w":float,"h":float,"theta":float  # rect
                 #    "r":float                           # circle
                 #  }, ...]
blocked = set()  # {(gx,gy), ...} in grid
blocked_dirty = True
lock = threading.Lock()

# ================== 유틸: 좌표 변환/클램프 ==================
def clamp(v, a, b): return a if v < a else b if v > b else v

def world_to_grid(x, z):
    gx = int(round(x * SCALE))
    gz = int(round(z * SCALE))
    return clamp(gx, 0, GRID_W-1), clamp(gz, 0, GRID_H-1)

def grid_to_world(gx, gz):
    return gx / SCALE, gz / SCALE

def in_bounds_g(gx, gy):
    return 0 <= gx < GRID_W and 0 <= gy < GRID_H

# ================== 장애물 스탬프 ==================
def stamp_circle(blocked_set, cx_w, cz_w, r_w, clearance_g):
    cx_g, cz_g = world_to_grid(cx_w, cz_w)
    r_g = int(round(r_w * SCALE)) + clearance_g
    r2  = r_g * r_g
    x0, x1 = cx_g - r_g, cx_g + r_g
    y0, y1 = cz_g - r_g, cz_g + r_g
    for gx in range(max(0, x0), min(GRID_W-1, x1)+1):
        dx = gx - cx_g
        dx2 = dx*dx
        # 원 내부(y범위)만 루프
        max_dy = int(math.isqrt(max(0, r2 - dx2)))
        yy0, yy1 = cz_g - max_dy, cz_g + max_dy
        for gy in range(max(0, yy0), min(GRID_H-1, yy1)+1):
            blocked_set.add((gx, gy))

def stamp_rect(blocked_set, cx_w, cz_w, w_w, h_w, theta_deg, clearance_g):
    # (회전 직사각형) → 그리드 격자 칠하기
    cx_g, cz_g = world_to_grid(cx_w, cz_w)
    hw_g = int(round((w_w * SCALE) / 2.0)) + clearance_g
    hh_g = int(round((h_w * SCALE) / 2.0)) + clearance_g

    # 바운딩 박스
    cos_t = math.cos(math.radians(theta_deg or 0.0))
    sin_t = math.sin(math.radians(theta_deg or 0.0))

    # 회전 사각형 꼭짓점(그리드) 계산
    corners = []
    for sx in (-hw_g, hw_g):
        for sy in (-hh_g, hh_g):
            rx = int(round(sx * cos_t - sy * sin_t)) + cx_g
            ry = int(round(sx * sin_t + sy * cos_t)) + cz_g
            corners.append((rx, ry))
    xs = [p[0] for p in corners]
    ys = [p[1] for p in corners]
    minx, maxx = max(0,min(xs)), min(GRID_W-1,max(xs))
    miny, maxy = max(0,min(ys)), min(GRID_H-1,max(ys))

    # 바운딩 박스 픽셀을 역회전시켜 사각형 내부여부 테스트
    for gx in range(minx, maxx+1):
        for gy in range(miny, maxy+1):
            # 점을 사각형 로컬 좌표계로
            lx = gx - cx_g
            ly = gy - cz_g
            # 역회전
            ux =  lx * cos_t + ly * sin_t
            uy = -lx * sin_t + ly * cos_t
            if -hw_g <= ux <= hw_g and -hh_g <= uy <= hh_g:
                blocked_set.add((gx, gy))

def rebuild_blocked():
    global blocked, blocked_dirty
    with lock:
        if not blocked_dirty:
            return
        b = set()
        for o in obstacles:
            typ = o.get("type","rect")
            if typ == "circle":
                r = float(o.get("r", OBST_DEFAULT_RADIUS))
                stamp_circle(b, float(o["cx"]), float(o["cz"]), r, CLEARANCE_GRID)
            else:
                w = float(o.get("w", OBST_DEFAULT_SIZE))
                h = float(o.get("h", OBST_DEFAULT_SIZE))
                th= float(o.get("theta", 0.0))
                stamp_rect(b, float(o["cx"]), float(o["cz"]), w, h, th, CLEARANCE_GRID)
        blocked = b
        blocked_dirty = False

# ================== 경로계획 (A* + LOS) ==================
def neighbors(gx, gy):
    steps = [(-1,0),(1,0),(0,-1),(0,1)]
    if ALLOW_DIAGONAL:
        steps += [(-1,-1),(-1,1),(1,-1),(1,1)]
    for dx, dy in steps:
        nx, ny = gx+dx, gy+dy
        if in_bounds_g(nx, ny):
            yield nx, ny

def heuristic(a, b):
    (x1,y1), (x2,y2) = a, b
    dx, dy = abs(x1-x2), abs(y1-y2)
    if ALLOW_DIAGONAL:
        D, D2 = 1.0, math.sqrt(2)
        return D*(dx+dy) + (D2-2*D)*min(dx,dy)     # 옥타일
    return dx + dy

def astar(start_g, goal_g, blocked_set):
    if start_g == goal_g: return [start_g]
    if start_g in blocked_set or goal_g in blocked_set: return []
    g = {start_g: 0.0}
    f = {start_g: heuristic(start_g, goal_g)}
    came = {}
    pq = [(f[start_g], start_g)]
    seen = set()
    D2 = math.sqrt(2)

    while pq:
        _, cur = heapq.heappop(pq)
        if cur in seen: continue
        seen.add(cur)
        if cur == goal_g:
            path = [cur]
            while cur in came:
                cur = came[cur]; path.append(cur)
            path.reverse()
            return path
        cx, cy = cur
        for nx, ny in neighbors(cx, cy):
            if (nx,ny) in blocked_set: continue
            step_cost = D2 if (nx!=cx and ny!=cy) else 1.0
            ng = g[cur] + step_cost
            if ng < g.get((nx,ny), 1e18):
                came[(nx,ny)] = cur
                g[(nx,ny)] = ng
                f[(nx,ny)] = ng + heuristic((nx,ny), goal_g)
                heapq.heappush(pq, (f[(nx,ny)], (nx,ny)))
    return []

def bresenham_line(x0, y0, x1, y1):
    dx = abs(x1 - x0); sx = 1 if x0 < x1 else -1
    dy = -abs(y1 - y0); sy = 1 if y0 < y1 else -1
    err = dx + dy
    x, y = x0, y0
    while True:
        yield (x,y)
        if x == x1 and y == y1: break
        e2 = 2*err
        if e2 >= dy:
            err += dy; x += sx
        if e2 <= dx:
            err += dx; y += sy

def line_blocked(p0, p1, blocked_set):
    for c in bresenham_line(p0[0], p0[1], p1[0], p1[1]):
        if c in blocked_set and c not in (p0, p1):
            return True
    return False

def simplify_path_los(path_g, blocked_set):
    if not path_g: return []
    simp = [path_g[0]]
    i = 0
    while i < len(path_g)-1:
        j = i + 1
        while j + 1 < len(path_g) and not line_blocked(path_g[i], path_g[j+1], blocked_set):
            j += 1
        simp.append(path_g[j])
        i = j
    return simp

def extract_turn_points(path_g):
    """그리드 경로에서 방향이 바뀌는 모서리만 골라서(첫/끝 포함) 월드 좌표로 반환"""
    if not path_g: return []
    out = [path_g[0]]
    for i in range(1, len(path_g)-1):
        x0,y0 = path_g[i-1]; x1,y1 = path_g[i]; x2,y2 = path_g[i+1]
        dx1, dy1 = (x1-x0, y1-y0)
        dx2, dy2 = (x2-x1, y2-y1)
        if (dx1,dy1) != (dx2,dy2):
            out.append((x1,y1))
    out.append(path_g[-1])
    # 그리드를 월드로
    return [ {"x": grid_to_world(x,y)[0], "z": grid_to_world(x,y)[1]} for (x,y) in out ]

# ================== 공통: 경로계획 래퍼 ==================
def plan_world(start_w, goal_w):
    rebuild_blocked()
    sx, sz = world_to_grid(start_w["x"], start_w["z"])
    gx, gz = world_to_grid(goal_w["x"],  goal_w["z"])
    path_g  = astar((sx,sz), (gx,gz), blocked)
    if not path_g: return [], [], []
    path2_g = simplify_path_los(path_g, blocked)
    # 월드 경로
    path_w = [ (grid_to_world(x,y)) for (x,y) in path2_g ]
    waypoints = [{"x":x, "z":z} for (x,z) in path_w]
    turns = extract_turn_points(path2_g)
    return path_g, waypoints, turns

# ================== API ==================
@app.route("/plan_initial", methods=["POST"])
def plan_initial():
    """
    {
      "start":{"x":30,"z":30},
      "goal":{"x":280,"z":280},
      "obstacles":[
         {"type":"rect","cx":120,"cz":180,"w":25,"h":40,"theta":15},
         {"type":"circle","cx":200,"cz":100,"r":14}
      ]
    }
    """
    global obstacles, blocked_dirty
    data = request.get_json(silent=True) or {}
    start = data.get("start", {"x":30,"z":30})
    goal  = data.get("goal",  {"x":280,"z":280})
    obs   = data.get("obstacles", [])
    with lock:
        if obs:
            obstacles = []
            for o in obs:
                typ = o.get("type","rect")
                if typ == "circle":
                    obstacles.append({
                        "type":"circle",
                        "cx":float(o["cx"]), "cz":float(o["cz"]),
                        "r": float(o.get("r", OBST_DEFAULT_RADIUS))
                    })
                else:
                    obstacles.append({
                        "type":"rect",
                        "cx":float(o["cx"]), "cz":float(o["cz"]),
                        "w": float(o.get("w", OBST_DEFAULT_SIZE)),
                        "h": float(o.get("h", OBST_DEFAULT_SIZE)),
                        "theta": float(o.get("theta", 0.0))
                    })
            blocked_dirty = True
    p_raw, wps, turns = plan_world(start, goal)
    if not wps:
        return jsonify({"ok": False, "error":"no-path"}), 409
    return jsonify({
        "ok": True,
        "path_len_raw": len(p_raw),
        "waypoints": wps,            # 월드 좌표
        "turn_points": turns         # 월드 좌표(코너)
    })

@app.route("/update_obstacles", methods=["POST"])
def update_obstacles():
    """
    {
      "add":[ {"type":"rect","cx":..,"cz":..,"w":..,"h":..,"theta":..}, {"type":"circle","cx":..,"cz":..,"r":..} ],
      "remove":[ {"cx":..,"cz":..,"type":"rect","w":..,"h":..,"theta":..} ]   # 간단 구현: '동일 파라미터' 매칭 시 제거
    }
    """
    global obstacles, blocked_dirty
    data = request.get_json(silent=True) or {}
    add = data.get("add", [])
    rem = data.get("remove", [])

    def norm_rect(o):
        return ("rect", round(float(o["cx"]),3), round(float(o["cz"]),3),
                round(float(o.get("w",OBST_DEFAULT_SIZE)),3),
                round(float(o.get("h",OBST_DEFAULT_SIZE)),3),
                round(float(o.get("theta",0.0)),3))
    def norm_circle(o):
        return ("circle", round(float(o["cx"]),3), round(float(o["cz"]),3),
                round(float(o.get("r",OBST_DEFAULT_RADIUS)),3))

    with lock:
        # 제거
        if rem:
            target = set()
            for o in rem:
                if o.get("type","rect") == "circle":
                    target.add(norm_circle(o))
                else:
                    target.add(norm_rect(o))
            new_list = []
            for o in obstacles:
                key = norm_circle(o) if o["type"]=="circle" else norm_rect(o)
                if key not in target:
                    new_list.append(o)
            obstacles = new_list

        # 추가
        for o in add:
            if o.get("type","rect") == "circle":
                obstacles.append({
                    "type":"circle",
                    "cx":float(o["cx"]), "cz":float(o["cz"]),
                    "r": float(o.get("r", OBST_DEFAULT_RADIUS))
                })
            else:
                obstacles.append({
                    "type":"rect",
                    "cx":float(o["cx"]), "cz":float(o["cz"]),
                    "w": float(o.get("w", OBST_DEFAULT_SIZE)),
                    "h": float(o.get("h", OBST_DEFAULT_SIZE)),
                    "theta": float(o.get("theta", 0.0))
                })
        blocked_dirty = True

    return jsonify({"ok": True, "count": len(obstacles)})

@app.route("/replan_from_pose", methods=["POST"])
def replan_from_pose():
    """
    { "pose":{"x":cur_x,"z":cur_z}, "goal":{"x":280,"z":280} }
    """
    data = request.get_json(silent=True) or {}
    pose = data.get("pose"); goal = data.get("goal")
    if not pose or not goal:
        return jsonify({"ok": False, "error":"need pose & goal"}), 400
    _, wps, turns = plan_world({"x":float(pose["x"]), "z":float(pose["z"])},
                               {"x":float(goal["x"]), "z":float(goal["z"])})
    if not wps:
        return jsonify({"ok": False, "error":"no-path"}), 409
    return jsonify({"ok": True, "waypoints": wps, "turn_points": turns})

@app.route("/status", methods=["GET"])
def status():
    # 디버그 용
    return jsonify({
        "world": [WORLD_W, WORLD_H],
        "grid": [GRID_W, GRID_H],
        "scale": SCALE,
        "clearance_world": CLEARANCE_WORLD,
        "clearance_grid": CLEARANCE_GRID,
        "obstacles_count": len(obstacles),
        "blocked_dirty": blocked_dirty
    })

if __name__ == "__main__":
    # 단순 개발 서버
    app.run(host="0.0.0.0", port=6000)
