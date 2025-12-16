# tpp.py
# TPP Flask service (IBSM-compatible)
from typing import List, Tuple, Set, Dict
import math, heapq
from flask import Flask, request, jsonify

# ----------------- Config / Parameters -----------------
GRID_W = 300
GRID_H = 300
ALLOW_DIAGONAL = True
CLEARANCE = 2
INCLUDE_DEBUG_IN_RESPONSE = True

app = Flask(__name__)

# ----------------- Utility / A* -----------------
def in_bounds(x: int, y: int, w:int, h:int) -> bool:
    return 0 <= x < w and 0 <= y < h

def neighbors(x: int, y: int, w:int, h:int, allow_diagonal=True):
    steps = [(-1,0),(1,0),(0,-1),(0,1)]
    if allow_diagonal:
        steps += [(-1,-1),(-1,1),(1,-1),(1,1)]
    for dx, dy in steps:
        nx, ny = x+dx, y+dy
        if in_bounds(nx, ny, w, h):
            yield nx, ny

def heuristic(a, b, allow_diagonal=True):
    (x1,y1),(x2,y2) = a,b
    dx, dy = abs(x1-x2), abs(y1-y2)
    if allow_diagonal:
        D, D2 = 1.0, math.sqrt(2.0)
        return D*(dx+dy) + (D2-2*D)*min(dx,dy)
    else:
        return dx + dy

def astar(start, goal, blocked:Set[Tuple[int,int]], grid_w:int, grid_h:int, allow_diagonal=True):
    if start == goal:
        return [start]
    if start in blocked or goal in blocked:
        return []
    D2 = math.sqrt(2.0)
    g = {start: 0.0}
    f = {start: heuristic(start, goal, allow_diagonal)}
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
                cur = came[cur]; path.append(cur)
            path.reverse()
            return path
        cx, cy = cur
        for nx, ny in neighbors(cx, cy, grid_w, grid_h, allow_diagonal):
            if (nx, ny) in blocked:
                continue
            step = D2 if (nx != cx and ny != cy) else 1.0
            ng = g[cur] + step
            if ng < g.get((nx, ny), 1e18):
                came[(nx, ny)] = cur
                g[(nx, ny)] = ng
                f[(nx, ny)] = ng + heuristic((nx, ny), goal, allow_diagonal)
                heapq.heappush(pq, (f[(nx, ny)], (nx, ny)))
    return []

# ----------------- LOS / simplify -----------------
def bresenham_line(x0,y0,x1,y1):
    dx = abs(x1-x0); sx = 1 if x0<x1 else -1
    dy = -abs(y1-y0); sy = 1 if y0<y1 else -1
    err = dx + dy
    while True:
        yield (x0,y0)
        if x0==x1 and y0==y1:
            break
        e2 = 2*err
        if e2 >= dy:
            err += dy; x0 += sx
        if e2 <= dx:
            err += dx; y0 += sy

def line_blocked(p0,p1,blocked:Set[Tuple[int,int]]):
    for c in bresenham_line(p0[0],p0[1],p1[0],p1[1]):
        if c in blocked and c not in (p0,p1):
            return True
    return False

def simplify_path(path:List[Tuple[int,int]], blocked:Set[Tuple[int,int]]):
    if not path:
        return []
    simp = [path[0]]
    i = 0
    while i < len(path)-1:
        j = i + 1
        while j + 1 < len(path) and not line_blocked(path[i], path[j+1], blocked):
            j += 1
        simp.append(path[j])
        i = j
    return simp

def find_turn_points(path:List[Tuple[int,int]]):
    if len(path) <= 2:
        return path[:]
    turns = [path[0]]
    for i in range(1, len(path)-1):
        v1 = (path[i][0]-path[i-1][0], path[i][1]-path[i-1][1])
        v2 = (path[i+1][0]-path[i][0], path[i+1][1]-path[i][1])
        if v1 != v2:
            turns.append(path[i])
    turns.append(path[-1])
    return turns

# ----------------- map_info parsing -----------------
def inflate_blocked(raw_blocked:Set[Tuple[int,int]], clearance:int, grid_w:int, grid_h:int) -> Set[Tuple[int,int]]:
    out = set()
    for (cx,cy) in raw_blocked:
        for dx in range(-clearance, clearance+1):
            for dy in range(-clearance, clearance+1):
                nx, ny = cx+dx, cy+dy
                if 0 <= nx < grid_w and 0 <= ny < grid_h:
                    out.add((nx, ny))
    return out

def map_info_to_blocked(map_info:Dict, grid_w:int, grid_h:int, clearance:int) -> Set[Tuple[int,int]]:
    raw = set()
    if not map_info:
        return set()
    try:
        if 'occupied' in map_info:
            for p in map_info['occupied']:
                try:
                    x = int(p[0]); y = int(p[1])
                except Exception:
                    continue
                if 0 <= x < grid_w and 0 <= y < grid_h:
                    raw.add((x,y))
        elif 'occupancy_grid' in map_info:
            og = map_info['occupancy_grid']
            h = len(og); w = len(og[0]) if h>0 else 0
            for row in range(h):
                for col in range(w):
                    if og[row][col]:
                        raw.add((col, row))
        elif 'obstacles' in map_info:
            for ob in map_info['obstacles']:
                cx = int(ob.get('cx', 0)); cy = int(ob.get('cy', 0)); size = int(ob.get('size',1))
                half = size // 2
                for x in range(cx-half, cx-half+size):
                    for y in range(cy-half, cy-half+size):
                        if 0 <= x < grid_w and 0 <= y < grid_h:
                            raw.add((x,y))
        else:
            print("TPP warning: unknown map_info format; treating empty.")
            return set()
    except Exception as e:
        print("TPP warning: exception while parsing map_info:", e)
        return set()
    blocked = inflate_blocked(raw, clearance, grid_w, grid_h)
    return blocked

def find_nearest_free(x:int, y:int, blocked:Set[Tuple[int,int]], grid_w:int, grid_h:int, max_radius:int=10):
    if (x,y) not in blocked:
        return (x,y)
    for r in range(1, max_radius+1):
        for dx in range(-r, r+1):
            for dy in range(-r, r+1):
                if abs(dx) != r and abs(dy) != r:
                    continue
                nx, ny = x+dx, y+dy
                if 0 <= nx < grid_w and 0 <= ny < grid_h and (nx,ny) not in blocked:
                    return (nx, ny)
    return None

# ----------------- core compute -----------------
def compute_waypoints(time: float,
                      ally_body_pos: Dict[str,float],
                      target_pos: Dict[str,float],
                      map_info: Dict) -> Dict:
    try:
        grid_w = map_info.get('grid_w', GRID_W) if isinstance(map_info, dict) else GRID_W
        grid_h = map_info.get('grid_h', GRID_H) if isinstance(map_info, dict) else GRID_H
        blocked = map_info_to_blocked(map_info, grid_w, grid_h, clearance=CLEARANCE)

        def read_coord(obj, *keys, default=0.0):
            for k in keys:
                if k in obj:
                    try:
                        return float(obj[k])
                    except Exception:
                        return float(default)
            return float(default)

        # ally_body_pos: IBSM sends {"x": player_x, "y": player_y, "z": player_z}
        # - ally grid X  <- ally_body_pos['x']
        # - ally grid Y (map Y) <- ally_body_pos['z']
        # - altitude for waypoints <- ally_body_pos['y'] (if ever needed)

        sx_f = read_coord(ally_body_pos, 'x', 'X')
        sy_f = read_coord(ally_body_pos, 'z', 'Z')   # map Y (used for path start)
        # target_pos: IBSM sends {"x": enemy_x, "y": enemy_y, "z": enemy_z}
        # - grid X <- target_pos['x']
        # - grid Y (map Y) <- target_pos['z']
        # - altitude (waypoint z coordinate) <- target_pos['y']
        gx_f = read_coord(target_pos, 'x', 'X')
        gy_f = read_coord(target_pos, 'z', 'Z')     # IMPORTANT: use 'z' as map Y
        z_f  = read_coord(target_pos, 'y', 'Y')     # altitude

        sx = int(round(sx_f)); sy = int(round(sy_f))
        gx = int(round(gx_f)); gy = int(round(gy_f))

        sx = max(0, min(grid_w-1, sx)); sy = max(0, min(grid_h-1, sy))
        gx = max(0, min(grid_w-1, gx)); gy = max(0, min(grid_h-1, gy))

        ns = find_nearest_free(sx, sy, blocked, grid_w, grid_h, max_radius=10)
        if ns is None:
            return {"waypoints_list": [], "target_pos": [float(gx_f), float(gy_f), float(z_f)],
                    "status":"ERROR", "message":"start blocked, no nearby free cell"}

        ng = find_nearest_free(gx, gy, blocked, grid_w, grid_h, max_radius=10)
        if ng is None:
            return {"waypoints_list": [], "target_pos": [float(gx_f), float(gy_f), float(z_f)],
                    "status":"ERROR", "message":"goal blocked, no nearby free cell"}

        path = astar(ns, ng, blocked, grid_w, grid_h, ALLOW_DIAGONAL)
        if not path:
            return {"waypoints_list": [], "target_pos": [float(gx_f), float(gy_f), float(z_f)],
                    "status":"NO_PATH", "message":"No path found"}

        path2 = simplify_path(path, blocked)
        turns = find_turn_points(path2)

        # IMPORTANT: return waypoints in IBSM/ADCS-friendly format: [x, z, altitude]
        # Here path nodes are (x_cell, y_cell) where we map second component -> z world coordinate.
        waypoints = [[float(p[0]), float(p[1]), float(z_f)] for p in turns]

        return {"waypoints_list": waypoints,
                "target_pos": [float(gx_f), float(gy_f), float(z_f)],
                "status":"OK",
                "message": f"path_len={len(path)}, simp_len={len(path2)}, turns={len(turns)}"}
    except Exception as e:
        tx = float(target_pos.get('x', target_pos.get('X', 0.0)))
        ty = float(target_pos.get('y', target_pos.get('Y', 0.0)))
        tz = float(target_pos.get('z', target_pos.get('Z', 0.0)))
        return {"waypoints_list": [], "target_pos": [tx, ty, tz],
                "status":"ERROR", "message": str(e)}

# ----------------- Flask endpoint -----------------
@app.route('/get_tpp', methods=['POST'])
def get_tpp():
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error":"empty request"}), 400

    time = data.get('time', 0.0)
    ally = data.get('ally_body_pos') or data.get('ally') or {}
    target = data.get('target_pos') or data.get('target') or {}
    map_info = data.get('map_info') or data.get('Map_info') or data.get('map') or data.get('Map') or {}

    if not ally or not target:
        return jsonify({"error":"ally_body_pos or target_pos missing"}), 400

    print("TPP /get_tpp request received:")
    print("  time:", time)
    print("  ally_body_pos:", ally)
    print("  target_pos:", target)
    print("  map_info keys:", list(map_info.keys()) if isinstance(map_info, dict) else repr(map_info))

    result = compute_waypoints(time, ally, target, map_info)

    resp = {
        "waypoints_list": result.get("waypoints_list", []),
        "target_pos": result.get("target_pos", [0.0, 0.0, 0.0])
    }
    if INCLUDE_DEBUG_IN_RESPONSE:
        resp["_debug"] = {"status": result.get("status"), "message": result.get("message")}

    print("TPP response being sent (summary): status =", result.get("status"), "| message =", result.get("message"))
    return jsonify(resp), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
