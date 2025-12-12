# -*- coding: utf-8 -*-
"""
TPP Flask service (IBSM-compatible response format)

입력 JSON 예시 (IBSM에서 보내는 형태 허용):
{
  "time": 123.4,
  "ally_body_pos": {"x": 30.5, "y": 30.2, "z": 0.0},   # 또는 {"X":..., "Y":..., "Z":...}
  "target_pos": {"x": 280.0, "y": 280.0, "z": 0.0},
  "map_info": { ... }
}

IBSM이 기대하는 응답 포맷(핵심):
{
  "waypoints_list": [ [x,y,z], ... ],   # float 리스트들
  "target_pos": [x, y, z]
}
(추가 디버그 필드가 필요하면 내부적으로 유지하나, 최종 응답 키는 위 두 가지만 필수)
"""
from typing import List, Tuple, Set, Dict, Optional
import math, heapq
from flask import Flask, request, jsonify

# ----------------- 파라미터 -----------------
GRID_W = 300
GRID_H = 300
ALLOW_DIAGONAL = True
CLEARANCE = 2        # TPP에서 적용 (셀 단위)
ARRIVAL_EPS = 1.0

# ---------------- 유틸 / A* (변경 없음) ----------------
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

# ---------------- LOS / simplify (변경 없음) ----------------
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

# ---------------- map_info -> blocked (팽창) ----------------
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
    # support occupied list
    if 'occupied' in map_info:
        for p in map_info['occupied']:
            x = int(p[0]); y = int(p[1])
            if 0 <= x < grid_w and 0 <= y < grid_h:
                raw.add((x,y))
    # support occupancy_grid
    elif 'occupancy_grid' in map_info:
        og = map_info['occupancy_grid']
        h = len(og); w = len(og[0]) if h>0 else 0
        # current assumption: og[0] -> y=0 (bottom). Adjust if IBSM uses top-first.
        for row in range(h):
            for col in range(w):
                if og[row][col]:
                    raw.add((col, row))
    # support obstacles list
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

    blocked = inflate_blocked(raw, clearance, grid_w, grid_h)
    return blocked

# ---------------- 보정 유틸 ----------------
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

# ---------------- 핵심 계산 함수 (내부 포맷 유지) ----------------
def compute_waypoints(time: float,
                      ally_body_pos: Dict[str,float],
                      target_pos: Dict[str,float],
                      map_info: Dict) -> Dict:
    """
    내부적으로 이전 포맷(Waypoints_list + dict target_pos)을 사용하여 계산 후,
    API 레이어에서 IBSM 포맷으로 변환하여 반환하도록 설계.
    """
    try:
        grid_w = map_info.get('grid_w', GRID_W) if isinstance(map_info, dict) else GRID_W
        grid_h = map_info.get('grid_h', GRID_H) if isinstance(map_info, dict) else GRID_H
        blocked = map_info_to_blocked(map_info, grid_w, grid_h, clearance=CLEARANCE)

        # ally_body_pos may contain 'X' or 'x' etc. Accept both
        def get_coord(obj, keys):
            for k in keys:
                if k in obj:
                    return float(obj[k])
            raise KeyError(f"Missing keys {keys} in object {obj}")

        sx_f = get_coord(ally_body_pos, ['X','x'])
        sy_f = get_coord(ally_body_pos, ['Y','y'])
        gx_f = get_coord(target_pos, ['x','X'])
        gy_f = get_coord(target_pos, ['y','Y'])
        z_f  = float(target_pos.get('z', target_pos.get('Z', 0.0)))

        sx = int(round(sx_f)); sy = int(round(sy_f))
        gx = int(round(gx_f)); gy = int(round(gy_f))

        sx = max(0, min(grid_w-1, sx)); sy = max(0, min(grid_h-1, sy))
        gx = max(0, min(grid_w-1, gx)); gy = max(0, min(grid_h-1, gy))

        ns = find_nearest_free(sx, sy, blocked, grid_w, grid_h, max_radius=10)
        if ns is None:
            return {"Waypoints_list": [], "target_pos": {"x":float(gx_f),"y":float(gy_f),"z":z_f},
                    "status":"ERROR", "message":"start blocked, no nearby free cell"}

        ng = find_nearest_free(gx, gy, blocked, grid_w, grid_h, max_radius=10)
        if ng is None:
            return {"Waypoints_list": [], "target_pos": {"x":float(gx_f),"y":float(gy_f),"z":z_f},
                    "status":"ERROR", "message":"goal blocked, no nearby free cell"}

        path = astar(ns, ng, blocked, grid_w, grid_h, ALLOW_DIAGONAL)
        if not path:
            return {"Waypoints_list": [], "target_pos": {"x":float(gx_f),"y":float(gy_f),"z":z_f},
                    "status":"NO_PATH", "message":"No path found"}

        path2 = simplify_path(path, blocked)
        turns = find_turn_points(path2)

        waypoints = [[float(p[0]), float(p[1]), float(z_f)] for p in turns]

        return {"Waypoints_list": waypoints,
                "target_pos": {"x": float(gx_f), "y": float(gy_f), "z": float(z_f)},
                "status":"OK",
                "message": f"path_len={len(path)}, simp_len={len(path2)}, turns={len(turns)}"}
    except Exception as e:
        return {"Waypoints_list": [], "target_pos": {"x":float(target_pos.get('x',0.0)),
                                                     "y":float(target_pos.get('y',0.0)),
                                                     "z":float(target_pos.get('z',0.0))},
                "status":"ERROR", "message": str(e)}

# ---------------- Flask endpoint (IBSM-compatible output) ----------------
app = Flask(__name__)

@app.route('/get_tpp', methods=['POST'])
def api_get_tpp():
    """
    입력은 IBSM과 합의된 형태(ally_body_pos 소문자/대소 혼용 허용 등)를 받음.
    응답은 IBSM 예시와 동일하게 'waypoints_list' (list of [x,y,z]) 와 'target_pos' (list [x,y,z]) 로 반환.
    """
    data = request.get_json(force=True)
    time = data.get('time', 0.0)
    ally = data.get('ally_body_pos') or data.get('ally') or {}
    target = data.get('target_pos') or data.get('target') or {}
    map_info = data.get('Map_info') or data.get('map_info') or data.get('map') or data.get('Map') or {}

    if not ally or not target:
        # 요청 필수 필드 누락 -> 400
        return jsonify({"error":"ally_body_pos or target_pos missing"}), 400

    # 내부 계산 (기존 compute_waypoints 포맷)
    internal = compute_waypoints(time, ally, target, map_info)

    # 내부 결과에서 waypoints + target_pos 추출하여 IBSM 포맷으로 변환
    # internal["Waypoints_list"] 는 [[x,y,z], ...] 형태(이미 float)
    waypoints_list = internal.get("Waypoints_list", [])

    # IBSM expects "target_pos" as a list [x,y,z]
    tdict = internal.get("target_pos", {})
    tx = float(tdict.get("x", target.get("x", target.get("X", 0.0))))
    ty = float(tdict.get("y", target.get("y", target.get("Y", 0.0))))
    tz = float(tdict.get("z", target.get("z", target.get("Z", 0.0))))
    target_pos_list = [tx, ty, tz]

    # Build IBSM-compatible response
    resp = {
        "waypoints_list": waypoints_list,
        "target_pos": target_pos_list
    }

    # Optionally include debug fields when needed (comment out in production)
    # resp["_debug"] = {"status": internal.get("status"), "message": internal.get("message")}

    return jsonify(resp)

if __name__ == '__main__':
    # 개발 서버 (IBSM 테스트용)
    app.run(host='0.0.0.0', port=5000, debug=True)
