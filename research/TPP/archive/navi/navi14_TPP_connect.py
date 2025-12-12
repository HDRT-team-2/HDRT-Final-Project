# -*- coding: utf-8 -*-
"""
TPP Flask service
POST /get_tpp
입력 JSON (example):
{
  "time": 123.4,
  "ally_body_pos": {"X": 30, "Y": 30, "Z": 0},
  "target_pos": {"x": 280, "y": 280, "z": 0},
  "map_info": { ... }  # supported formats documented below
}

반환 JSON:
{
  "Waypoints_list": [[x,y,z], ...],  # float
  "target_pos": {"x":..,"y":..,"z":..},
  "status": "OK" / "NO_PATH" / "ERROR",
  "message": "..."
}
"""
from typing import List, Tuple, Set, Dict, Optional
import math, heapq, json
from flask import Flask, request, jsonify

# ----------------- 파라미터 -----------------
GRID_W = 300
GRID_H = 300
ALLOW_DIAGONAL = True
CLEARANCE = 2        # 요청대로 TPP에서 CLEARANCE=2 적용
ARRIVAL_EPS = 1.0

# --------------- 유틸리티 / A* ---------------
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
        if cur in seen: continue
        seen.add(cur)
        if cur == goal:
            path = [cur]
            while cur in came:
                cur = came[cur]; path.append(cur)
            path.reverse(); return path
        cx, cy = cur
        for nx, ny in neighbors(cx, cy, grid_w, grid_h, allow_diagonal):
            if (nx, ny) in blocked: continue
            step = D2 if (nx != cx and ny != cy) else 1.0
            ng = g[cur] + step
            if ng < g.get((nx, ny), 1e18):
                came[(nx, ny)] = cur
                g[(nx, ny)] = ng
                f[(nx, ny)] = ng + heuristic((nx, ny), goal, allow_diagonal)
                heapq.heappush(pq, (f[(nx, ny)], (nx, ny)))
    return []

# --------------- LOS / simplification ---------------
def bresenham_line(x0,y0,x1,y1):
    dx = abs(x1-x0); sx = 1 if x0<x1 else -1
    dy = -abs(y1-y0); sy = 1 if y0<y1 else -1
    err = dx + dy
    while True:
        yield (x0,y0)
        if x0==x1 and y0==y1: break
        e2 = 2*err
        if e2 >= dy: err += dy; x0 += sx
        if e2 <= dx: err += dx; y0 += sy

def line_blocked(p0,p1,blocked:Set[Tuple[int,int]]):
    for c in bresenham_line(p0[0],p0[1],p1[0],p1[1]):
        if c in blocked and c not in (p0,p1):
            return True
    return False

def simplify_path(path:List[Tuple[int,int]], blocked:Set[Tuple[int,int]]):
    if not path: return []
    simp=[path[0]]; i=0
    while i < len(path)-1:
        j = i+1
        while j+1 < len(path) and not line_blocked(path[i], path[j+1], blocked):
            j += 1
        simp.append(path[j]); i = j
    return simp

def find_turn_points(path:List[Tuple[int,int]]):
    if len(path) <= 2: return path[:]
    turns = [path[0]]
    for i in range(1, len(path)-1):
        v1 = (path[i][0]-path[i-1][0], path[i][1]-path[i-1][1])
        v2 = (path[i+1][0]-path[i][0], path[i+1][1]-path[i][1])
        if v1 != v2:
            turns.append(path[i])
    turns.append(path[-1])
    return turns

# --------------- Map_info -> blocked (CLEARANCE 적용) ---------------
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
    """
    지원되는 map_info 포맷:
    1) {'grid_w':w,'grid_h':h,'occupied': [[x,y],...]}
    2) {'occupancy_grid': [[0/1,...], ...]}  # row-major: occupancy_grid[row][col], row -> y
    3) {'obstacles': [{'cx':x,'cy':y,'size':S}, ...]}  # size: 정사각 한 변 길이(셀)
    """
    raw = set()
    if not map_info:
        return set()
    if 'occupied' in map_info:
        for p in map_info['occupied']:
            x = int(p[0]); y = int(p[1])
            if 0 <= x < grid_w and 0 <= y < grid_h:
                raw.add((x,y))
    elif 'occupancy_grid' in map_info:
        og = map_info['occupancy_grid']
        h = len(og); w = len(og[0]) if h>0 else 0
        # assume og[row][col], row 0 is bottom row? user said origin is bottom-left.
        # We assume og[0] corresponds to y=0 (bottom). If IBSM uses top-row-first, this must be adapted.
        for row in range(h):
            for col in range(w):
                if og[row][col]:
                    raw.add((col, row))
    elif 'obstacles' in map_info:
        for ob in map_info['obstacles']:
            cx = int(ob['cx']); cy = int(ob['cy']); size = int(ob.get('size',1))
            half = size // 2
            for x in range(cx-half, cx-half+size):
                for y in range(cy-half, cy-half+size):
                    if 0 <= x < grid_w and 0 <= y < grid_h:
                        raw.add((x,y))
    else:
        raise ValueError("map_info 형식 불명. supported: 'occupied', 'occupancy_grid', 'obstacles'")

    # 팽창 적용 (TPP가 CLEARANCE=2 적용)
    blocked = inflate_blocked(raw, clearance, grid_w, grid_h)
    return blocked

# ------------- 보정 (시작/목표가 막혀있을 때 근접 빈셀 찾기) -------------
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

# ---------------- TPP compute ----------------
def compute_waypoints(time: float,
                      ally_body_pos: Dict[str,float],
                      target_pos: Dict[str,float],
                      map_info: Dict) -> Dict:
    try:
        # 1) grid size (user said 300x300)
        grid_w = map_info.get('grid_w', GRID_W) if isinstance(map_info, dict) else GRID_W
        grid_h = map_info.get('grid_h', GRID_H) if isinstance(map_info, dict) else GRID_H
        # 2) blocked set
        blocked = map_info_to_blocked(map_info, grid_w, grid_h, clearance=CLEARANCE)

        # 3) start/goal from ally_body_pos / target_pos (cells, origin bottom-left)
        sx = int(round(ally_body_pos['X'])); sy = int(round(ally_body_pos['Y']))
        gx = int(round(target_pos['x'])); gy = int(round(target_pos['y']))

        # clamp
        sx = max(0, min(grid_w-1, sx)); sy = max(0, min(grid_h-1, sy))
        gx = max(0, min(grid_w-1, gx)); gy = max(0, min(grid_h-1, gy))

        # 4) if start/goal blocked, find nearest free
        ns = find_nearest_free(sx, sy, blocked, grid_w, grid_h, max_radius=10)
        if ns is None:
            return {"Waypoints_list": [], "target_pos": {"x":float(gx),"y":float(gy),"z":float(target_pos.get('z',0.0))},
                    "status":"ERROR", "message":"start blocked, no nearby free cell"}
        ng = find_nearest_free(gx, gy, blocked, grid_w, grid_h, max_radius=10)
        if ng is None:
            return {"Waypoints_list": [], "target_pos": {"x":float(gx),"y":float(gy),"z":float(target_pos.get('z',0.0))},
                    "status":"ERROR", "message":"goal blocked, no nearby free cell"}

        path = astar(ns, ng, blocked, grid_w, grid_h, ALLOW_DIAGONAL)
        if not path:
            return {"Waypoints_list": [], "target_pos": {"x":float(gx),"y":float(gy),"z":float(target_pos.get('z',0.0))},
                    "status":"NO_PATH", "message":"No path found"}

        path2 = simplify_path(path, blocked)
        turns = find_turn_points(path2)

        z = float(target_pos.get('z', 0.0))
        waypoints = [[float(p[0]), float(p[1]), z] for p in turns]

        return {"Waypoints_list": waypoints,
                "target_pos": {"x": float(gx), "y": float(gy), "z": z},
                "status":"OK",
                "message": f"path_len={len(path)}, simp_len={len(path2)}, turns={len(turns)}"}
    except Exception as e:
        return {"Waypoints_list": [], "target_pos": {"x":float(target_pos.get('x',0.0)),
                                                     "y":float(target_pos.get('y',0.0)),
                                                     "z":float(target_pos.get('z',0.0))},
                "status":"ERROR", "message": str(e)}

# ---------------- Flask endpoint ----------------
app = Flask(__name__)

@app.route('/get_tpp', methods=['POST'])
def api_get_tpp():
    data = request.get_json(force=True)
    time = data.get('time', 0.0)
    ally = data.get('ally_body_pos')
    target = data.get('target_pos')
    map_info = data.get('Map_info') or data.get('map_info') or data.get('map') or data.get('Map') or {}
    if ally is None or target is None:
        return jsonify({"status":"ERROR","message":"ally_body_pos or target_pos missing"}), 400
    out = compute_waypoints(time, ally, target, map_info)
    return jsonify(out)

if __name__ == '__main__':
    # 로컬에서 개발/테스트용: python tpp_service.py
    app.run(host='0.0.0.0', port=5000, debug=True)
