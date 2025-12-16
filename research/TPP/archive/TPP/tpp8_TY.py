# ============================================================
# TPP (Tank Path Planning) Server - IBSM2 Compatible Version
# - 3D dict 기반 입출력 구조
# - A* + LOS path simplification
# - target_pos(list/dict) 모두 지원, dict로 정규화해서 반환
# ============================================================

from flask import Flask, request, jsonify
import math
import heapq
from typing import List, Tuple, Set

app = Flask(__name__)

# ------------------ A* Path Planner 설정 -------------------
GRID_W, GRID_H = 300, 300
ALLOW_DIAGONAL = True
OBST_SIZE      = 20
OBST_HALF      = OBST_SIZE // 2
CLEARANCE      = 3

# -----------------------------------------------------------
# 기본 유틸
# -----------------------------------------------------------
def in_bounds(x: int, y: int) -> bool:
    return 0 <= x < GRID_W and 0 <= y < GRID_H

def neighbors(x: int, y: int):
    steps = [(-1,0),(1,0),(0,-1),(0,1)]
    if ALLOW_DIAGONAL:
        steps += [(-1,-1),(-1,1),(1,-1),(1,1)]
    for dx, dy in steps:
        nx, ny = x + dx, y + dy
        if in_bounds(nx, ny):
            yield nx, ny

def heuristic(a: Tuple[int,int], b: Tuple[int,int]) -> float:
    (x1,y1), (x2,y2) = a, b
    dx, dy = abs(x1-x2), abs(y1-y2)
    if ALLOW_DIAGONAL:
        D, D2 = 1.0, math.sqrt(2.0)
        return D*(dx+dy) + (D2-2*D)*min(dx,dy)
    else:
        return dx + dy

def stamp_square(blocked: Set[Tuple[int,int]], cx: int, cy: int, half: int):
    x0, x1 = cx - half, cx + half - 1
    y0, y1 = cy - half, cy + half - 1
    for x in range(x0, x1+1):
        for y in range(y0, y1+1):
            if in_bounds(x, y):
                blocked.add((x, y))


# -----------------------------------------------------------
# A*
# -----------------------------------------------------------
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


# -----------------------------------------------------------
# LOS 단순화
# -----------------------------------------------------------
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

def line_blocked(p0, p1, blocked: Set[Tuple[int,int]]) -> bool:
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


# ============================================================
# /get_tpp
# ============================================================
@app.route('/get_tpp', methods=['POST'])
def get_tpp():
    data = request.get_json(force=True)
    print("TPP /get_tpp request_data:", data)

    # ---------------- ally_body_pos ----------------
    ally = data.get("ally_body_pos", {})
    ally_x = float(ally.get("x", 0.0))
    ally_y = float(ally.get("y", 0.0))
    ally_z = float(ally.get("z", 0.0))

    start_grid = (
        max(0, min(GRID_W - 1, int(round(ally_x)))),
        max(0, min(GRID_H - 1, int(round(ally_z))))
    )

    # ---------------- target_pos ----------------
    tp = data.get("target_pos", {"x": 0.0, "y": 0.0, "z": 0.0})

    if isinstance(tp, list):
        if len(tp) == 3:
            target_x, target_y, target_z = tp
        else:
            target_x, target_y, target_z = 0.0, 0.0, 0.0
    elif isinstance(tp, dict):
        target_x = float(tp.get("x", 0.0))
        target_y = float(tp.get("y", 0.0))
        target_z = float(tp.get("z", 0.0))
    else:
        target_x, target_y, target_z = 0.0, 0.0, 0.0

    target_pos = {
        "x": target_x,
        "y": target_y,
        "z": target_z
    }

    goal_grid = (
        max(0, min(GRID_W - 1, int(round(target_x)))),
        max(0, min(GRID_H - 1, int(round(target_z))))
    )

    # ---------------- unknowns -> blocked ----------------
    unknowns = data.get("unknowns", [])
    blocked: Set[Tuple[int,int]] = set()
    infl_half = OBST_HALF + CLEARANCE

    for obj in unknowns:
        pos = obj.get("position", {})
        ux = float(pos.get("x", 0.0))
        uz = float(pos.get("z", 0.0))

        cx = max(0, min(GRID_W - 1, int(round(ux))))
        cz = max(0, min(GRID_H - 1, int(round(uz))))

        stamp_square(blocked, cx, cz, infl_half)

    # ---------------- A* Path + LOS ----------------
    path = astar(start_grid, goal_grid, blocked)
    if path:
        path = simplify_path_los(path, blocked)

    # ---------------- Convert to 3D dict waypoints ----------------
    waypoints_list = []
    if path:
        for (gx, gz) in path:
            waypoints_list.append({
                "x": float(gx),
                "y": float(ally_y),
                "z": float(gz)
            })
    else:
        waypoints_list.append({
            "x": target_x,
            "y": ally_y,
            "z": target_z
        })

    response = {
        "waypoints": waypoints_list,
        "target_pos": target_pos
    }

    print("TPP /get_tpp response:", response)
    return jsonify(response)


# ============================================================
# Main
# ============================================================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
